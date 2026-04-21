"""全市场 A 股日线数据层。

职责：
1. 在 import akshare 之前完成网络预处理（清代理环境变量 + 覆盖 requests.Session
   为 `trust_env=False` 且带浏览器请求头），避免 akshare 内部会话继承到不可用的
   系统代理。
2. 提供多源 fallback 的单只日线获取：tencent -> sina -> eastmoney。
3. 过滤 A 股股票池：沪深主板 + 创业板 + 科创板，排除北交所。
4. 把全市场日线落到 parquet，并做 TTL/原子写盘。

输出 schema: ``date / open / high / low / close / volume / symbol``。
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

# 沪深主板 / 中小板 / 创业板 / 科创板 的代码前缀，排除北交所（4/8/9 开头）。
UNIVERSE_PREFIXES: tuple[str, ...] = (
    "60",   # 沪市主板
    "688",  # 科创板
    "000",  # 深市主板
    "001",  # 深市主板
    "002",  # 中小板（并入主板）
    "003",  # 深市主板
    "300",  # 创业板
    "301",  # 创业板
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


def _with_market_prefix(symbol: str) -> str:
    """为新浪/腾讯接口补齐 ``sh/sz/bj`` 市场前缀。"""
    code = symbol.zfill(6)
    if code.startswith(("5", "6", "9", "11", "13")):
        return f"sh{code}"
    if code.startswith(("0", "2", "3")):
        return f"sz{code}"
    if code.startswith(("4", "8")):
        return f"bj{code}"
    return f"sh{code}"


def is_in_universe(symbol: str) -> bool:
    """判断代码是否属于沪深主板/创业板/科创板。"""
    code = symbol.zfill(6)
    return code.startswith(UNIVERSE_PREFIXES)


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

    out["symbol"] = symbol.zfill(6)
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
    """获取沪深主板 / 创业板 / 科创板的 6 位代码列表（排除北交所）。"""
    if ak is None:
        raise ModuleNotFoundError("akshare is not installed")

    frame = ak.stock_info_a_code_name()
    code_col = "code" if "code" in frame.columns else frame.columns[0]
    codes = frame[code_col].astype(str).str.zfill(6)
    mask = pd.Series(False, index=codes.index)
    for prefix in UNIVERSE_PREFIXES:
        mask = mask | codes.str.startswith(prefix)
    return codes[mask].tolist()


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
    """加载全市场 A 股日线；必要时联网重建并写 parquet。

    :param refresh: 强制重建（忽略 TTL 和现存文件）。
    """
    # 延迟导入配置以便测试时可以 monkey-patch
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


def refresh_ashare_daily() -> dict[str, int | str]:
    """对外暴露的手动刷新入口，返回落盘摘要。"""
    dataset = load_ashare_daily(refresh=True)
    distinct_symbols = dataset.select(pl.col("symbol").n_unique()).item()
    return {
        "rows": dataset.height,
        "symbols": distinct_symbols,
        "path": str(_resolve_parquet_path()),
    }


def _resolve_parquet_path() -> Path:
    from app.config import get_daily_parquet_path

    return get_daily_parquet_path()
