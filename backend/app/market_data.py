"""Tushare 数据层（替代 AKShare / BaoStock）。

全模块对 ``pro.daily`` / ``stock_basic`` / ``daily_basic`` 等请求统一做
**每分钟请求数滑动窗口限流**（默认 500 次/分钟，见 ``get_tushare_max_requests_per_minute``），
多线程拉取时会在限额内自动排队，避免触发 Tushare 频控。

输出三张 parquet：
- 日线: ``date / open / high / low / close / volume / symbol``
- 名称: ``symbol / name``
- PE: ``symbol / pe_ratio``
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock, RLock
from typing import Iterable

import pandas as pd
import polars as pl

from app.config import (
    get_daily_cache_ttl_hours,
    get_daily_history_days,
    get_market_refresh_cooldown_hours,
    get_tushare_max_requests_per_minute,
    get_tushare_max_workers,
    get_tushare_token,
    get_tushare_daily_parquet_path,
)

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

try:
    import tushare as ts
except ImportError:  # pragma: no cover - optional dependency guard
    ts = None  # type: ignore[assignment]

def _get_pro():
    if ts is None:
        raise ModuleNotFoundError("tushare is not installed")
    ts.set_token(get_tushare_token())
    return ts.pro_api()


_TUSHARE_RL_LOCK = Lock()
_TUSHARE_RL_TIMES: deque[float] = deque()
_TUSHARE_RL_WINDOW_SEC = 60.0


def _acquire_tushare_request_slot() -> None:
    """在并发拉取时限制 Tushare 请求频率（默认 500 次/分钟，滑动窗口）。"""
    limit = get_tushare_max_requests_per_minute()
    window = _TUSHARE_RL_WINDOW_SEC
    while True:
        sleep_for = 0.0
        with _TUSHARE_RL_LOCK:
            now = time.monotonic()
            while _TUSHARE_RL_TIMES and _TUSHARE_RL_TIMES[0] <= now - window:
                _TUSHARE_RL_TIMES.popleft()
            if len(_TUSHARE_RL_TIMES) < limit:
                _TUSHARE_RL_TIMES.append(now)
                return
            sleep_for = _TUSHARE_RL_TIMES[0] + window - now + 0.005
        time.sleep(max(sleep_for, 0.01))


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


def _to_ts_code(symbol: str) -> str:
    code = _normalize_symbol(symbol)
    if code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "1", "2", "3")):
        return f"{code}.SZ"
    return f"{code}.SH"


def is_in_universe(symbol: str) -> bool:
    """判断代码是否属于股票池（股票或 A 股 ETF）。"""
    return _is_stock_symbol(symbol) or _is_etf_symbol(symbol)


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


def _fetch_tushare_daily(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    _acquire_tushare_request_slot()
    pro = _get_pro()
    raw = pro.daily(
        ts_code=_to_ts_code(symbol),
        start_date=start_date,
        end_date=end_date,
    )
    if raw is None or raw.empty:
        raise RuntimeError("tushare daily returned empty data")
    return _normalize(
        raw,
        symbol=symbol,
        column_mapping={
            "trade_date": "date",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "vol": "volume",
        },
    )


def fetch_daily_one(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    adjust: str = "qfq",
    sources: Iterable[tuple[str, object]] | None = None,
) -> pd.DataFrame:
    del adjust, sources
    return _fetch_tushare_daily(symbol, start_date, end_date)


# ---------------------------------------------------------------------------
# 股票池
# ---------------------------------------------------------------------------


def list_universe() -> list[str]:
    """获取股票池代码列表：当前为 A 股股票（不含北交所）。"""
    _acquire_tushare_request_slot()
    pro = _get_pro()
    raw = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="symbol",
    )
    if raw is None or raw.empty:
        raise RuntimeError("tushare stock_basic returned empty data")
    merged = (
        pd.DataFrame({"symbol": raw["symbol"].astype(str).map(_normalize_symbol)})
        .loc[lambda x: x["symbol"].map(_is_stock_symbol)]
        .drop_duplicates(subset=["symbol"])
        .sort_values("symbol")
        .reset_index(drop=True)
    )
    return merged["symbol"].tolist()


# ---------------------------------------------------------------------------
# 全市场日线 parquet 缓存
# ---------------------------------------------------------------------------


_CACHE_LOCK = RLock()

_MARKET_REFRESH_MARKER = "market_refresh.json"


def _market_refresh_marker_path() -> Path:
    """与日线 parquet 同目录，记录最近一次全市场刷新成功的时间戳。"""
    return get_tushare_daily_parquet_path().parent / _MARKET_REFRESH_MARKER


def _read_market_refresh_unix() -> float | None:
    path = _market_refresh_marker_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data.get("unix_ts")
        if raw is None:
            return None
        return float(raw)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _write_market_refresh_unix() -> None:
    path = _market_refresh_marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"unix_ts": time.time()}, separators=(",", ":")),
        encoding="utf-8",
    )


def get_market_data_cache_revision() -> float:
    """本地全市场数据版本号，供评分结果与前端缓存失效判断。

    取 ``market_refresh.json`` 中的成功刷新时间与日线 parquet 的 ``mtime`` 较大者；
    任一方更新则数值变大。
    """
    path = get_tushare_daily_parquet_path()
    m_parquet = path.stat().st_mtime if path.is_file() else 0.0
    m_refresh = _read_market_refresh_unix()
    if m_refresh is None:
        return float(m_parquet)
    return float(max(m_refresh, m_parquet))


def _within_market_refresh_cooldown() -> tuple[bool, float | None, int]:
    """若仍在冷却窗口内则 (True, last_unix, hours)；否则 (False, last_unix, hours)。"""
    hours = get_market_refresh_cooldown_hours()
    if hours <= 0:
        return False, _read_market_refresh_unix(), hours
    last = _read_market_refresh_unix()
    if last is None:
        return False, None, hours
    if time.time() - last < hours * 3600:
        return True, last, hours
    return False, last, hours


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


def load_tushare_daily(*, refresh: bool = False) -> pl.DataFrame:
    """读取/重建 Tushare 日线缓存。"""
    path = get_tushare_daily_parquet_path()

    with _CACHE_LOCK:
        if not refresh and _parquet_is_fresh(path, get_daily_cache_ttl_hours()):
            LOGGER.info("loading daily parquet from cache: %s", path)
            return pl.read_parquet(path)

        LOGGER.info("rebuilding daily parquet -> %s", path)
        dataset = _build_daily_dataset(
            history_days=get_daily_history_days(),
            max_workers=get_tushare_max_workers(),
        )
        _write_parquet_atomic(dataset, path)
        return dataset

# ---------------------------------------------------------------------------
# 股票名称 & PE 快照
# ---------------------------------------------------------------------------


def _sibling_parquet(name: str) -> Path:
    return get_tushare_daily_parquet_path().parent / name


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


def _fetch_stock_names() -> pd.DataFrame:
    _acquire_tushare_request_slot()
    pro = _get_pro()
    raw = pro.stock_basic(
        exchange="",
        list_status="L",
        fields="symbol,name",
    )
    if raw is None or raw.empty:
        raise RuntimeError("tushare stock_basic for names returned empty data")
    return (
        pd.DataFrame(
            {
                "symbol": raw["symbol"].astype(str).map(_normalize_symbol),
                "name": raw["name"].astype(str).str.strip(),
            }
        )
        .dropna(subset=["symbol", "name"])
        .drop_duplicates(subset=["symbol"])
        .reset_index(drop=True)
    )


def load_stock_names(*, refresh: bool = False) -> pl.DataFrame:
    """加载 ``symbol / name`` 快照（股票池 = 股票 + ETF）。"""
    path = _stock_names_path()

    with _CACHE_LOCK:
        if not refresh and _parquet_is_fresh(path, get_daily_cache_ttl_hours()):
            return pl.read_parquet(path)

        dataset = pl.from_pandas(_fetch_stock_names())
        _write_parquet_atomic(dataset, path)
        LOGGER.info("stock_names snapshot rebuilt: %d rows -> %s", dataset.height, path)
        return dataset


def _fetch_pe_one(symbol: str) -> float | None:
    """逐只拉取最新 PE，优先 PE_TTM。"""
    _acquire_tushare_request_slot()
    pro = _get_pro()
    end_date = datetime.now().strftime("%Y%m%d")
    start_date = (datetime.now() - timedelta(days=120)).strftime("%Y%m%d")
    raw = pro.daily_basic(
        ts_code=_to_ts_code(symbol),
        start_date=start_date,
        end_date=end_date,
        fields="trade_date,pe_ttm,pe",
    )
    if raw is None or raw.empty:
        return None
    for candidate in ("pe_ttm", "pe"):
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
    updated_at = datetime.now().isoformat(timespec="seconds")
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
            rows.append(
                {
                    "symbol": symbol,
                    "pe_ratio": pe_value,
                    "updated_at": updated_at,
                }
            )

    if not rows:
        raise RuntimeError("no pe rows fetched successfully")

    LOGGER.info(
        "pe snapshot built: ok=%d, missing/failed=%d",
        len(rows),
        len(tickers) - len(rows),
    )
    return pl.DataFrame(rows)


def load_pe_snapshot(*, refresh: bool = False) -> pl.DataFrame:
    """加载 ``symbol / pe_ratio`` 快照（只读本地，不自动联网拉取）。"""
    path = _pe_snapshot_path()

    with _CACHE_LOCK:
        if not refresh and _parquet_is_fresh(path, get_daily_cache_ttl_hours()):
            return pl.read_parquet(path)
        try:
            snapshot = _build_pe_snapshot(max_workers=get_tushare_max_workers())
            _write_parquet_atomic(snapshot, path)
            return snapshot
        except Exception as exc:  # noqa: BLE001
            if path.exists():
                LOGGER.warning("rebuild pe snapshot failed, reusing stale cache: %s", exc)
                return pl.read_parquet(path)
            raise


# ---------------------------------------------------------------------------
# 增量刷新辅助函数
# ---------------------------------------------------------------------------


INCREMENTAL_OVERLAP_DAYS = 5


def _merge_daily_frames(existing: pl.DataFrame, updates: pl.DataFrame) -> pl.DataFrame:
    return (
        pl.concat([existing, updates], how="vertical_relaxed")
        .unique(subset=["symbol", "date"], keep="last")
        .sort(["symbol", "date"])
    )


def _update_stock_names_incremental(universe: list[str]) -> tuple[pl.DataFrame, dict[str, object]]:
    path = _stock_names_path()
    rows_before = 0
    if path.exists():
        existing = pl.read_parquet(path)
        rows_before = existing.height
    else:
        existing = pl.DataFrame(schema={"symbol": pl.Utf8, "name": pl.Utf8})

    fresh = pl.from_pandas(_fetch_stock_names()).filter(pl.col("symbol").is_in(universe)).sort("symbol")
    merged = (
        pl.concat(
            [
                existing.filter(~pl.col("symbol").is_in(fresh.get_column("symbol"))),
                fresh,
            ],
            how="vertical_relaxed",
        )
        .unique(subset=["symbol"], keep="last")
        .sort("symbol")
    )
    _write_parquet_atomic(merged, path)
    return merged, {
        "rows_before": rows_before,
        "rows_after": merged.height,
        "upserted_symbols": fresh.height,
        "path": str(path),
    }


def _build_pe_snapshot_incremental(
    *,
    max_workers: int,
    universe: list[str],
) -> tuple[pl.DataFrame, dict[str, object]]:
    path = _pe_snapshot_path()
    stock_universe = [symbol for symbol in universe if _is_stock_symbol(symbol)]
    if not stock_universe:
        raise RuntimeError("empty stock universe — cannot build incremental pe snapshot")

    rows_before = 0
    targets: list[str]
    if path.exists():
        existing = pl.read_parquet(path)
        rows_before = existing.height
        snapshot_cols = existing.columns
        if "updated_at" in snapshot_cols:
            stale_expr = (
                pl.col("updated_at")
                .str.strptime(pl.Datetime, strict=False)
                .dt.date()
                .fill_null(date(1970, 1, 1))
            )
            today = datetime.now().date()
            stale_symbols = (
                existing.filter(stale_expr < today)
                .get_column("symbol")
                .unique()
                .to_list()
            )
        else:
            stale_symbols = existing.get_column("symbol").unique().to_list()
        existing_symbols = set(existing.get_column("symbol").unique().to_list())
        targets = sorted(set(stale_symbols) | (set(stock_universe) - existing_symbols))
    else:
        existing = pl.DataFrame(schema={"symbol": pl.Utf8, "pe_ratio": pl.Float64})
        targets = stock_universe

    if not targets:
        return existing, {
            "rows_before": rows_before,
            "rows_after": existing.height,
            "updated_symbols": 0,
            "path": str(path),
        }

    updates = _build_pe_snapshot(max_workers=max_workers, universe=targets)
    merged = (
        pl.concat(
            [existing.filter(~pl.col("symbol").is_in(updates.get_column("symbol"))), updates],
            how="vertical_relaxed",
        )
        .unique(subset=["symbol"], keep="last")
        .sort("symbol")
    )
    _write_parquet_atomic(merged, path)
    return merged, {
        "rows_before": rows_before,
        "rows_after": merged.height,
        "updated_symbols": updates.height,
        "path": str(path),
    }


def _refresh_market_data_incremental() -> dict[str, object]:
    path = _resolve_parquet_path()
    history_days = get_daily_history_days()
    max_workers = get_tushare_max_workers()
    universe = list_universe()
    end_date = datetime.now()
    fallback_start = end_date - timedelta(days=history_days)
    end_date_str = end_date.strftime("%Y%m%d")

    with _CACHE_LOCK:
        existing = pl.read_parquet(path) if path.exists() else pl.DataFrame(schema={
            "date": pl.Datetime,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
            "symbol": pl.Utf8,
        })

        rows_before = existing.height
        latest_dates: dict[str, datetime] = {}
        if existing.height > 0:
            latest = existing.group_by("symbol").agg(pl.col("date").max().alias("last_date"))
            for row in latest.iter_rows(named=True):
                last_date = row["last_date"]
                if isinstance(last_date, datetime):
                    latest_dates[str(row["symbol"])] = last_date

        frames: list[pd.DataFrame] = []
        failed: list[str] = []
        refreshed_symbols: list[str] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {}
            for symbol in universe:
                last_date = latest_dates.get(symbol)
                if last_date is None:
                    start_dt = fallback_start
                else:
                    start_dt = max(
                        fallback_start,
                        last_date - timedelta(days=INCREMENTAL_OVERLAP_DAYS),
                    )
                future = executor.submit(
                    fetch_daily_one,
                    symbol,
                    start_dt.strftime("%Y%m%d"),
                    end_date_str,
                    adjust="qfq",
                )
                future_map[future] = symbol

            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    frame = future.result()
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("incremental daily fetch failed for %s: %s", symbol, exc)
                    failed.append(symbol)
                    continue
                if frame.empty:
                    continue
                frames.append(frame)
                refreshed_symbols.append(symbol)

        if frames:
            updates = pl.from_pandas(
                pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"])
            )
            daily = _merge_daily_frames(existing, updates)
            _write_parquet_atomic(daily, path)
        else:
            daily = existing

        _names, names_summary = _update_stock_names_incremental(universe)
        try:
            _pe, pe_summary = _build_pe_snapshot_incremental(
                max_workers=max_workers,
                universe=universe,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("incremental PE refresh failed: %s", exc)
            pe_summary = {
                "status": "failed",
                "error": str(exc),
                "path": str(_pe_snapshot_path()),
            }

    return {
        "mode": "incremental",
        "daily": {
            "rows_before": rows_before,
            "rows_after": daily.height,
            "rows_added": max(0, daily.height - rows_before),
            "updated_symbols": len(set(refreshed_symbols)),
            "failed_symbols": len(failed),
            "path": str(path),
        },
        "names": names_summary,
        "pe": pe_summary,
    }


# ---------------------------------------------------------------------------
# 对外手动刷新入口
# ---------------------------------------------------------------------------


def refresh_market_data(*, mode: str = "full", force: bool = False) -> dict[str, object]:
    """刷新市场缓存。

    ``mode='full'``: 全量重建 daily / names / pe 三张 parquet。
    ``mode='incremental'``: 日线按 symbol 最后日期补拉，名称做 upsert，PE 按日增量。

    ``force=True`` 时跳过「距上次成功刷新不足冷却窗口」的短路（供单股/回测补数等内部调用）。
    手动 ``POST /refresh`` 默认受 ``DDTRADING_MARKET_REFRESH_COOLDOWN_HOURS`` 约束（默认 24h）。
    """
    if not force:
        cooling, last_unix, cd_hours = _within_market_refresh_cooldown()
        if cooling:
            return {
                "skipped": True,
                "reason": "cooldown",
                "cooldown_hours": cd_hours,
                "last_refresh_unix": last_unix,
                "message": (
                    f"距上次全市场刷新不足 {cd_hours} 小时，已跳过。"
                    " 需要立即更新请使用 POST /refresh?force=true 。"
                ),
            }

    if mode == "incremental":
        summary = _refresh_market_data_incremental()
        _write_market_refresh_unix()
        return summary
    if mode != "full":
        raise ValueError("refresh mode must be either 'full' or 'incremental'")

    daily = load_tushare_daily(refresh=True)
    names = load_stock_names(refresh=True)
    _write_market_refresh_unix()

    return {
        "mode": "full",
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
            "status": "skipped",
            "reason": "auto PE refresh disabled",
            "path": str(_pe_snapshot_path()),
        },
    }


def _fetch_single_stock_name(symbol: str) -> str | None:
    """尽力拉取单只股票中文名，失败返回 None。"""
    code = _normalize_symbol(symbol)
    try:
        frame = _fetch_stock_names()
        matched = frame.loc[frame["symbol"] == code]
        if not matched.empty:
            return str(matched.iloc[0]["name"]).strip() or None
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("single-name lookup failed: %s", exc)
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
    row = pl.DataFrame(
        {
            "symbol": [symbol],
            "pe_ratio": [pe_value],
            "updated_at": [datetime.now().isoformat(timespec="seconds")],
        }
    )
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
    """按需把单只股票的 daily / 名称增量写入本地 parquet 缓存。

    用于 ``/score`` 单股路径冷命中时按需补齐——不重建全市场，只追加/覆盖这一只。

    - 非股票池代码（北交所或非法）→ ``ValueError``
    - ETF → ``ValueError``（评分管线不支持 ETF）
    - daily 拉不到 → 上抛 ``RuntimeError``（多源 fallback 都失败）
    - PE 自动拉取默认关闭：不会在此函数内联网抓取 PE
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
    end_date_str = datetime.now().strftime("%Y%m%d")
    start_date_str = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")

    daily_pd = fetch_daily_one(code, start_date_str, end_date_str, adjust=adjust)
    if daily_pd.empty:
        raise RuntimeError(f"fetched daily is empty for {code}")
    new_daily = pl.from_pandas(daily_pd)

    name = _fetch_single_stock_name(code)

    with _CACHE_LOCK:
        daily_rows = _upsert_daily(new_daily, code)
        if name:
            _upsert_name(code, name)

    LOGGER.info(
        "ensure_symbol_cached: %s -> daily=%d rows, name=%r",
        code,
        daily_rows,
        name,
    )

    pe_value = _fetch_pe_one(code)
    if pe_value is not None:
        with _CACHE_LOCK:
            _upsert_pe(code, pe_value)

    return {
        "symbol": code,
        "daily_rows": daily_rows,
        "pe_ratio": pe_value,
        "name": name,
        "window": {"start": start_date_str, "end": end_date_str},
    }


def refresh_tushare_daily() -> dict[str, int | str]:
    """仅刷新日线 parquet（不触发 PE/名称刷新）。"""
    dataset = load_tushare_daily(refresh=True)
    return {
        "rows": dataset.height,
        "symbols": dataset.select(pl.col("symbol").n_unique()).item(),
        "path": str(_resolve_parquet_path()),
    }


def _resolve_parquet_path() -> Path:
    return get_tushare_daily_parquet_path()
