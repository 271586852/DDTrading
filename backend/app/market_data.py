"""A 股股票 + ETF 日线数据层。

职责：
1. 在 import akshare 之前完成网络预处理（清代理环境变量 + 覆盖 requests.Session
   为 `trust_env=False` 且带浏览器请求头），避免 akshare 内部会话继承到不可用的
   系统代理。
2. 提供多源 fallback 的单只日线获取：tencent -> sina -> eastmoney。
3. 维护股票池：沪深主板 + 创业板 + 科创板 + A 股 ETF，排除北交所。
4. 把全市场日线落到 parquet，并做 TTL/原子写盘。
5. 额外维护两张轻量面板：股票名称快照 `stock_names.parquet`，PE 快照
   `pe_snapshot.parquet`（东财 ``stock_value_em`` 估值分析最新一行，优先
   PE(TTM)，回退 PE(静)）。

日线 schema: ``date / open / high / low / close / volume / symbol``。
名称 schema: ``symbol / name``；PE schema: ``symbol / pe_ratio``。
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Callable, Iterable

import pandas as pd
import polars as pl


LOGGER = logging.getLogger(__name__)

REQUIRED_COLS = ["date", "open", "high", "low", "close", "volume", "symbol"]

# 沪深主板 / 中小板 / 创业板 / 科创板 的股票代码前缀，排除北交所。
STOCK_UNIVERSE_PREFIXES: tuple[str, ...] = (
    "60",   # 沪市主板
    "688",  # 科创板
    "000",  # 深市主板
    "001",  # 深市主板
    "002",  # 中小板（并入主板）
    "003",  # 深市主板
    "300",  # 创业板
    "301",  # 创业板
)

# A 股场内 ETF 常见前缀。真正的 ETF 名单仍以新浪 ETF 列表接口为准；
# 这里主要用于判断 symbol 类型，以及为新浪/腾讯日线接口补齐市场前缀。
ETF_PREFIXES: tuple[str, ...] = (
    "15",
    "16",
    "50",
    "51",
    "52",
    "56",
    "58",
)


_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}


def _configure_requests_environment() -> None:
    """清代理环境变量并覆盖 ``requests.Session`` 为不信任环境且带浏览器头的子类。

    该函数必须在 ``import akshare`` 之前调用，否则 akshare 内部模块级的 session
    会拿到旧版 Session，patch 无效。
    """
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(key, None)

    import requests  # 延迟导入以免模块级副作用顺序不对

    original_session_cls = requests.Session

    class _NoProxyBrowserSession(original_session_cls):
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            super().__init__(*args, **kwargs)
            self.trust_env = False
            self.proxies = {}
            self.headers.update(_BROWSER_HEADERS)

    requests.Session = _NoProxyBrowserSession  # type: ignore[assignment]
    requests.sessions.Session = _NoProxyBrowserSession  # type: ignore[assignment]


_configure_requests_environment()


try:
    import akshare as ak  # noqa: E402  # must be imported AFTER the patch above
except ImportError:  # pragma: no cover - optional dependency guard
    ak = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 股票代码工具
# ---------------------------------------------------------------------------


def _normalize_symbol(symbol: str) -> str:
    """把 ``sh600000`` / ``sz159998`` / ``600000`` 统一转成 6 位代码。"""
    text = str(symbol).strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if text.startswith(prefix):
            text = text[len(prefix):]
            break

    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise ValueError(f"invalid symbol: {symbol!r}")
    return digits[-6:].zfill(6)


def _is_stock_symbol(symbol: str) -> bool:
    code = _normalize_symbol(symbol)
    return code.startswith(STOCK_UNIVERSE_PREFIXES)


def _is_etf_symbol(symbol: str) -> bool:
    code = _normalize_symbol(symbol)
    return code.startswith(ETF_PREFIXES)


def _with_market_prefix(symbol: str) -> str:
    """为新浪/腾讯接口补齐 ``sh/sz/bj`` 市场前缀。"""
    code = _normalize_symbol(symbol)
    if code.startswith(("11", "13")):
        return f"sh{code}"
    if code.startswith(("0", "1", "2", "3")):
        return f"sz{code}"
    if code.startswith(("5", "6", "9")):
        return f"sh{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sh{code}"


def is_in_universe(symbol: str) -> bool:
    """判断代码是否属于股票池（股票或 A 股 ETF）。"""
    return _is_stock_symbol(symbol) or _is_etf_symbol(symbol)


def _frame_from_code_name(
    raw: pd.DataFrame,
    *,
    code_col: str,
    name_col: str,
) -> pd.DataFrame:
    return (
        pd.DataFrame(
            {
                "symbol": raw[code_col].astype(str).map(_normalize_symbol),
                "name": raw[name_col].astype(str).str.strip(),
            }
        )
        .dropna(subset=["symbol", "name"])
        .reset_index(drop=True)
    )


def _fetch_sina_stock_snapshot() -> pd.DataFrame:
    raw = ak.stock_zh_a_spot()
    code_col = "代码" if "代码" in raw.columns else "code"
    name_col = "名称" if "名称" in raw.columns else "name"
    frame = _frame_from_code_name(raw, code_col=code_col, name_col=name_col)
    return frame.loc[frame["symbol"].map(_is_stock_symbol)].reset_index(drop=True)


def _fetch_sina_etf_snapshot() -> pd.DataFrame:
    raw = ak.fund_etf_category_sina(symbol="ETF基金")
    code_col = "代码" if "代码" in raw.columns else raw.columns[0]
    name_col = "名称" if "名称" in raw.columns else raw.columns[1]
    frame = _frame_from_code_name(raw, code_col=code_col, name_col=name_col)
    return frame.drop_duplicates(subset=["symbol"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------


def _normalize(
    raw: pd.DataFrame,
    *,
    symbol: str,
    column_mapping: dict[str, str],
) -> pd.DataFrame:
    missing = [col for col in column_mapping if col not in raw.columns]
    if missing:
        raise RuntimeError(
            f"source returned unexpected columns. missing={missing}, "
            f"got={list(raw.columns)}"
        )

    out = raw[list(column_mapping.keys())].rename(columns=column_mapping).copy()
    out["date"] = pd.to_datetime(out["date"])
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out["symbol"] = _normalize_symbol(symbol)
    out = (
        out.dropna(subset=["open", "high", "low", "close"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    return out[REQUIRED_COLS]


# ---------------------------------------------------------------------------
# 数据源适配
# ---------------------------------------------------------------------------


def _fetch_tencent(
    symbol: str, start_date: str, end_date: str, adjust: str
) -> pd.DataFrame:
    raw = ak.stock_zh_a_hist_tx(
        symbol=_with_market_prefix(symbol),
        start_date=start_date,
        end_date=end_date,
        adjust=adjust or "",
    )
    if raw is None or raw.empty:
        raise RuntimeError("tencent returned empty data")
    return _normalize(
        raw,
        symbol=symbol,
        column_mapping={
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "amount": "volume",
        },
    )


def _fetch_sina(
    symbol: str, start_date: str, end_date: str, adjust: str
) -> pd.DataFrame:
    raw = ak.stock_zh_a_daily(
        symbol=_with_market_prefix(symbol),
        start_date=start_date,
        end_date=end_date,
        adjust=adjust or "",
    )
    if raw is None or raw.empty:
        raise RuntimeError("sina returned empty data")
    return _normalize(
        raw,
        symbol=symbol,
        column_mapping={
            "date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        },
    )


def _fetch_eastmoney(
    symbol: str, start_date: str, end_date: str, adjust: str
) -> pd.DataFrame:
    raw = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=adjust or "",
    )
    if raw is None or raw.empty:
        raise RuntimeError("eastmoney returned empty data")
    return _normalize(
        raw,
        symbol=symbol,
        column_mapping={
            "\u65e5\u671f": "date",        # 日期
            "\u5f00\u76d8": "open",        # 开盘
            "\u6700\u9ad8": "high",        # 最高
            "\u6700\u4f4e": "low",         # 最低
            "\u6536\u76d8": "close",       # 收盘
            "\u6210\u4ea4\u91cf": "volume",  # 成交量
        },
    )


FetcherFn = Callable[[str, str, str, str], pd.DataFrame]

DATA_SOURCES: list[tuple[str, FetcherFn]] = [
    ("tencent", _fetch_tencent),
    ("sina", _fetch_sina),
    ("eastmoney", _fetch_eastmoney),
]


def fetch_daily_one(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    adjust: str = "qfq",
    sources: Iterable[tuple[str, FetcherFn]] | None = None,
) -> pd.DataFrame:
    """按顺序尝试多个数据源，任意一个成功即返回。"""
    if ak is None:
        raise ModuleNotFoundError("akshare is not installed")

    last_exc: Exception | None = None
    for name, fetcher in sources or DATA_SOURCES:
        try:
            return fetcher(symbol, start_date, end_date, adjust)
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("source %s failed for %s: %r", name, symbol, exc)
            last_exc = exc

    raise RuntimeError(f"all sources failed for {symbol}: {last_exc!r}")


# ---------------------------------------------------------------------------
# 股票池
# ---------------------------------------------------------------------------


def list_universe() -> list[str]:
    """获取股票池代码列表：A 股股票 + A 股场内 ETF。"""
    if ak is None:
        raise ModuleNotFoundError("akshare is not installed")

    stocks = _fetch_sina_stock_snapshot()
    etfs = _fetch_sina_etf_snapshot()
    merged = (
        pd.concat([stocks[["symbol"]], etfs[["symbol"]]], ignore_index=True)
        .drop_duplicates(subset=["symbol"])
        .sort_values("symbol")
        .reset_index(drop=True)
    )
    return merged["symbol"].tolist()


# ---------------------------------------------------------------------------
# 全市场日线 parquet 缓存
# ---------------------------------------------------------------------------


_CACHE_LOCK = Lock()


def _parquet_is_fresh(path: Path, ttl_hours: int) -> bool:
    if not path.exists():
        return False
    if ttl_hours <= 0:
        return True  # 0 表示永不自动刷新
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds < ttl_hours * 3600


def _write_parquet_atomic(df: pl.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=target.parent
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        df.write_parquet(tmp_path)
        os.replace(tmp_path, target)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def _build_daily_dataset(
    *,
    history_days: int,
    max_workers: int,
    universe: list[str] | None = None,
) -> pl.DataFrame:
    if ak is None:
        raise ModuleNotFoundError("akshare is not installed")

    end_date_str = datetime.now().strftime("%Y%m%d")
    start_date_str = (
        datetime.now() - timedelta(days=history_days)
    ).strftime("%Y%m%d")

    tickers = universe if universe is not None else list_universe()
    if not tickers:
        raise RuntimeError("empty universe — cannot build daily dataset")

    LOGGER.info(
        "building daily dataset: %d symbols, %s ~ %s, workers=%d",
        len(tickers),
        start_date_str,
        end_date_str,
        max_workers,
    )

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                fetch_daily_one, sym, start_date_str, end_date_str, adjust="qfq"
            ): sym
            for sym in tickers
        }
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                frames.append(future.result())
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("fetch failed for %s: %s", symbol, exc)
                failed.append(symbol)

    if not frames:
        raise RuntimeError("no symbol fetched successfully")

    LOGGER.info(
        "daily dataset built: ok=%d, failed=%d",
        len(frames),
        len(failed),
    )

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values(["symbol", "date"]).reset_index(drop=True)
    return pl.from_pandas(merged)


def load_ashare_daily(*, refresh: bool = False) -> pl.DataFrame:
    """加载股票池日线（A 股股票 + ETF）；必要时联网重建并写 parquet。"""
    from app.config import (
        get_akshare_max_workers,
        get_daily_cache_ttl_hours,
        get_daily_history_days,
        get_daily_parquet_path,
    )

    path = get_daily_parquet_path()

    with _CACHE_LOCK:
        if not refresh and _parquet_is_fresh(path, get_daily_cache_ttl_hours()):
            LOGGER.info("loading daily parquet from cache: %s", path)
            return pl.read_parquet(path)

        LOGGER.info("rebuilding daily parquet -> %s", path)
        dataset = _build_daily_dataset(
            history_days=get_daily_history_days(),
            max_workers=get_akshare_max_workers(),
        )
        _write_parquet_atomic(dataset, path)
        return dataset


# ---------------------------------------------------------------------------
# 股票名称 & PE 快照
# ---------------------------------------------------------------------------


def _sibling_parquet(name: str) -> Path:
    from app.config import get_daily_parquet_path

    return get_daily_parquet_path().parent / name


def _stock_names_path() -> Path:
    return _sibling_parquet("stock_names.parquet")


def _pe_snapshot_path() -> Path:
    return _sibling_parquet("pe_snapshot.parquet")


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:  # NaN check
        return None
    return parsed


def _fetch_stock_names_primary() -> pd.DataFrame:
    stocks = _fetch_sina_stock_snapshot()
    etfs = _fetch_sina_etf_snapshot()
    return (
        pd.concat([stocks, etfs], ignore_index=True)
        .drop_duplicates(subset=["symbol"])
        .reset_index(drop=True)
    )


def _fetch_stock_names_fallback() -> pd.DataFrame:
    """退路：东财 A 股快照 + 新浪 ETF 列表。"""
    frames: list[pd.DataFrame] = []
    last_exc: Exception | None = None

    try:
        raw = ak.stock_zh_a_spot_em()
        code_col = "\u4ee3\u7801" if "\u4ee3\u7801" in raw.columns else "code"
        name_col = "\u540d\u79f0" if "\u540d\u79f0" in raw.columns else "name"
        stocks = _frame_from_code_name(raw, code_col=code_col, name_col=name_col)
        frames.append(stocks.loc[stocks["symbol"].map(_is_stock_symbol)])
    except Exception as exc:  # noqa: BLE001
        last_exc = exc

    try:
        frames.append(_fetch_sina_etf_snapshot())
    except Exception as exc:  # noqa: BLE001
        last_exc = exc

    if not frames:
        raise RuntimeError(f"all fallback stock_names loaders failed: {last_exc!r}")

    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates(subset=["symbol"])
        .reset_index(drop=True)
    )


def load_stock_names(*, refresh: bool = False) -> pl.DataFrame:
    """加载 ``symbol / name`` 快照（股票池 = 股票 + ETF）。"""
    from app.config import get_daily_cache_ttl_hours

    path = _stock_names_path()

    with _CACHE_LOCK:
        if not refresh and _parquet_is_fresh(path, get_daily_cache_ttl_hours()):
            return pl.read_parquet(path)

        if ak is None:
            raise ModuleNotFoundError("akshare is not installed")

        last_exc: Exception | None = None
        frame: pd.DataFrame | None = None
        for loader in (_fetch_stock_names_primary, _fetch_stock_names_fallback):
            try:
                frame = loader()
                LOGGER.info("stock_names loaded via %s", loader.__name__)
                break
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("stock_names loader %s failed: %s", loader.__name__, exc)
                last_exc = exc
        if frame is None:
            if path.exists():
                LOGGER.warning(
                    "all stock_names loaders failed (%r); reusing stale parquet at %s",
                    last_exc,
                    path,
                )
                return pl.read_parquet(path)
            raise RuntimeError(f"all stock_names loaders failed: {last_exc!r}")

        filtered = (
            frame.drop_duplicates(subset=["symbol"])
            .reset_index(drop=True)
        )

        dataset = pl.from_pandas(filtered)
        _write_parquet_atomic(dataset, path)
        LOGGER.info("stock_names snapshot rebuilt: %d rows -> %s", dataset.height, path)
        return dataset


def _fetch_pe_one(symbol: str) -> float | None:
    """使用东财 ``stock_value_em`` 拉取最新 PE。

    返回列含 ``PE(TTM)`` 与 ``PE(静)``，优先取 TTM。
    """
    raw = ak.stock_value_em(symbol=symbol)
    if raw is None or raw.empty:
        return None
    for candidate in ("PE(TTM)", "PE(\u9759)"):  # PE(静)
        if candidate in raw.columns:
            cleaned = raw.dropna(subset=[candidate])
            if cleaned.empty:
                continue
            value = _to_float(cleaned.iloc[-1][candidate])
            if value is not None and value > 0:
                return value
    return None


def _build_pe_snapshot(
    *, max_workers: int, universe: list[str] | None = None
) -> pl.DataFrame:
    if ak is None:
        raise ModuleNotFoundError("akshare is not installed")

    source = universe if universe is not None else list_universe()
    tickers = [sym for sym in source if _is_stock_symbol(sym)]
    if not tickers:
        raise RuntimeError("empty universe — cannot build pe snapshot")

    LOGGER.info(
        "building pe snapshot for %d symbols (workers=%d)",
        len(tickers),
        max_workers,
    )

    rows: list[dict[str, object]] = []
    failed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_fetch_pe_one, sym): sym for sym in tickers
        }
        for future in as_completed(future_map):
            symbol = future_map[future]
            try:
                pe_value = future.result()
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("pe fetch failed for %s: %s", symbol, exc)
                failed += 1
                continue
            if pe_value is None:
                continue
            rows.append({"symbol": symbol, "pe_ratio": pe_value})

    if not rows:
        raise RuntimeError("no pe rows fetched successfully")

    LOGGER.info(
        "pe snapshot built: ok=%d, missing/failed=%d",
        len(rows),
        len(tickers) - len(rows),
    )
    return pl.DataFrame(rows)


def load_pe_snapshot(*, refresh: bool = False) -> pl.DataFrame:
    """加载 ``symbol / pe_ratio`` 快照；必要时联网重建并写 parquet。"""
    from app.config import get_akshare_max_workers, get_daily_cache_ttl_hours

    path = _pe_snapshot_path()

    with _CACHE_LOCK:
        if not refresh and _parquet_is_fresh(path, get_daily_cache_ttl_hours()):
            return pl.read_parquet(path)

        dataset = _build_pe_snapshot(max_workers=get_akshare_max_workers())
        _write_parquet_atomic(dataset, path)
        return dataset


# ---------------------------------------------------------------------------
# 对外手动刷新入口
# ---------------------------------------------------------------------------


def refresh_market_data() -> dict[str, object]:
    """一站式刷新：全市场日线 + 名称 + PE 快照，返回落盘摘要。"""
    daily = load_ashare_daily(refresh=True)
    names = load_stock_names(refresh=True)
    pe_snapshot = load_pe_snapshot(refresh=True)

    return {
        "daily": {
            "rows": daily.height,
            "symbols": daily.select(pl.col("symbol").n_unique()).item(),
            "path": str(_resolve_parquet_path()),
        },
        "names": {
            "rows": names.height,
            "path": str(_stock_names_path()),
        },
        "pe": {
            "rows": pe_snapshot.height,
            "path": str(_pe_snapshot_path()),
        },
    }


def _fetch_single_stock_name(symbol: str) -> str | None:
    """尽力从 spot 接口捞一个股票中文名，失败返回 None。"""
    code = _normalize_symbol(symbol)
    for loader in (_fetch_sina_stock_snapshot, _fetch_stock_names_fallback):
        try:
            frame = loader()
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("single-name loader %s failed: %s", loader.__name__, exc)
            continue
        matched = frame.loc[frame["symbol"] == code]
        if not matched.empty:
            return str(matched.iloc[0]["name"]).strip() or None
    return None


def _upsert_daily(new_daily: pl.DataFrame, symbol: str) -> int:
    path = _resolve_parquet_path()
    if path.exists():
        existing = pl.read_parquet(path)
        merged = pl.concat(
            [existing.filter(pl.col("symbol") != symbol), new_daily],
            how="vertical_relaxed",
        ).sort(["symbol", "date"])
    else:
        merged = new_daily.sort(["symbol", "date"])
    _write_parquet_atomic(merged, path)
    return new_daily.height


def _upsert_pe(symbol: str, pe_value: float) -> None:
    path = _pe_snapshot_path()
    row = pl.DataFrame({"symbol": [symbol], "pe_ratio": [pe_value]})
    if path.exists():
        existing = pl.read_parquet(path)
        merged = pl.concat(
            [existing.filter(pl.col("symbol") != symbol), row],
            how="vertical_relaxed",
        )
    else:
        merged = row
    _write_parquet_atomic(merged, path)


def _upsert_name(symbol: str, name: str) -> None:
    path = _stock_names_path()
    row = pl.DataFrame({"symbol": [symbol], "name": [name]})
    if path.exists():
        existing = pl.read_parquet(path)
        merged = pl.concat(
            [existing.filter(pl.col("symbol") != symbol), row],
            how="vertical_relaxed",
        )
    else:
        merged = row
    _write_parquet_atomic(merged, path)


def ensure_symbol_cached(
    symbol: str,
    *,
    days: int = 365,
    adjust: str = "qfq",
) -> dict[str, object]:
    """按需把单只股票的 daily / PE / 名称增量写入三张 parquet 缓存。

    用于 ``/score`` 单股路径冷命中时按需补齐——不重建全市场，只追加/覆盖这一只。

    - 非股票池代码（北交所或非法）→ ``ValueError``
    - ETF → ``ValueError``（评分管线不支持 ETF）
    - daily 拉不到 → 上抛 ``RuntimeError``（多源 fallback 都失败）
    - PE 拉不到 → 不致命，只落 daily/name；上层评分会因缺 PE 继续 404
    """
    code = _normalize_symbol(symbol)

    if _is_etf_symbol(code):
        raise ValueError(
            f"Symbol '{code}' is an ETF, which is not supported by the scoring pipeline."
        )
    if not _is_stock_symbol(code):
        raise ValueError(
            f"Symbol '{code}' is not in the supported universe "
            "(A-share main board / GEM / STAR; Beijing Stock Exchange excluded)."
        )
    if ak is None:
        raise ModuleNotFoundError("akshare is not installed")

    end_date_str = datetime.now().strftime("%Y%m%d")
    start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    daily_pd = fetch_daily_one(code, start_date_str, end_date_str, adjust=adjust)
    if daily_pd.empty:
        raise RuntimeError(f"fetched daily is empty for {code}")
    new_daily = pl.from_pandas(daily_pd)

    try:
        pe_value = _fetch_pe_one(code)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("pe fetch failed for %s: %s", code, exc)
        pe_value = None

    name = _fetch_single_stock_name(code)

    with _CACHE_LOCK:
        daily_rows = _upsert_daily(new_daily, code)
        if pe_value is not None:
            _upsert_pe(code, pe_value)
        if name:
            _upsert_name(code, name)

    LOGGER.info(
        "ensure_symbol_cached: %s -> daily=%d rows, pe=%s, name=%r",
        code,
        daily_rows,
        pe_value,
        name,
    )

    return {
        "symbol": code,
        "daily_rows": daily_rows,
        "pe_ratio": pe_value,
        "name": name,
        "window": {"start": start_date_str, "end": end_date_str},
    }


def refresh_ashare_daily() -> dict[str, int | str]:
    """仅刷新日线 parquet（不触发 PE/名称刷新）。"""
    dataset = load_ashare_daily(refresh=True)
    return {
        "rows": dataset.height,
        "symbols": dataset.select(pl.col("symbol").n_unique()).item(),
        "path": str(_resolve_parquet_path()),
    }


def _resolve_parquet_path() -> Path:
    from app.config import get_daily_parquet_path

    return get_daily_parquet_path()
