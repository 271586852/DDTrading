"""Tushare 数据层（DuckDB 本地缓存）。

全模块对 ``pro.daily`` / ``stock_basic`` / ``daily_basic`` 等请求统一做
**滑动窗口 + 最小请求间隔**限流（见 ``get_tushare_max_requests_per_minute``），
缓解「自然分钟」边界与纯滑动窗口不一致导致的 500 次/分钟超限。

输出三张 DuckDB 表：
- daily_bars: ``date / open / high / low / close / volume / symbol``
- stock_names: ``symbol / name``
- pe_snapshot: ``symbol / pe_ratio``
"""
from __future__ import annotations

import logging
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
)
from app.common import market_repository as repo

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
# 两次获准发起 Tushare 请求之间的最小间隔（秒），与滑动窗口叠加，压低自然分钟边界上的突发。
_TUSHARE_LAST_GRANT_MONO = 0.0


def _acquire_tushare_request_slot() -> None:
    """在并发拉取时限制 Tushare 请求频率（滑动窗口 + 最小间隔，避免触发频控）。"""
    limit = get_tushare_max_requests_per_minute()
    window = _TUSHARE_RL_WINDOW_SEC
    # 间隔按「略低于平台 500/ 分钟」折算，与 limit 取小，避免用户把 limit 设很低时间隔仍过短。
    spacing_rpm = max(60, int(min(limit, 500) * 0.88))
    min_gap = 60.0 / spacing_rpm
    global _TUSHARE_LAST_GRANT_MONO
    while True:
        sleep_for = 0.0
        with _TUSHARE_RL_LOCK:
            now = time.monotonic()
            while _TUSHARE_RL_TIMES and _TUSHARE_RL_TIMES[0] <= now - window:
                _TUSHARE_RL_TIMES.popleft()
            gap_wait = _TUSHARE_LAST_GRANT_MONO + min_gap - now
            if len(_TUSHARE_RL_TIMES) >= limit:
                sleep_for = max(0.0, _TUSHARE_RL_TIMES[0] + window - now + 0.005)
            if gap_wait > 0:
                sleep_for = max(sleep_for, gap_wait)
            if sleep_for <= 0:
                _TUSHARE_RL_TIMES.append(now)
                _TUSHARE_LAST_GRANT_MONO = now
                return
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
        ts = _to_ts_code(symbol)
        raise RuntimeError(
            f"tushare daily returned empty data (ts_code={ts}, start={start_date}, end={end_date})"
        )
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
# 全市场日线 DuckDB 缓存
# ---------------------------------------------------------------------------


_CACHE_LOCK = RLock()

_MARKET_REFRESH_MARKER = "market_refresh.json"


def _market_refresh_marker_path() -> Path:
    """保留旧函数名用于兼容；刷新标记已迁入 DuckDB cache_meta。"""
    return repo.repository_path().with_name(_MARKET_REFRESH_MARKER)


def _read_market_refresh_unix() -> float | None:
    return repo.read_market_refresh_unix()


def _write_market_refresh_unix() -> None:
    repo.mark_market_refresh()


def get_market_data_cache_revision() -> float:
    """本地全市场数据版本号，供评分结果与前端缓存失效判断。"""
    return repo.cache_revision()


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


def _cache_is_fresh(path: Path, ttl_hours: int) -> bool:
    if not repo.has_daily_data():
        return False
    if ttl_hours <= 0:
        return True  # 0 表示永不自动刷新
    db_path = repo.repository_path()
    if not db_path.exists():
        return False
    age_seconds = time.time() - db_path.stat().st_mtime
    return age_seconds < ttl_hours * 3600


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

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values(["symbol", "date"]).reset_index(drop=True)
    return pl.from_pandas(merged)


def load_tushare_daily(*, refresh: bool = False) -> pl.DataFrame:
    """读取/重建 Tushare 日线缓存（DuckDB）。"""
    path = repo.repository_path()

    with _CACHE_LOCK:
        if not refresh and _cache_is_fresh(path, get_daily_cache_ttl_hours()):
            return repo.load_daily()

        dataset = _build_daily_dataset(
            history_days=get_daily_history_days(),
            max_workers=get_tushare_max_workers(),
        )
        repo.replace_daily(dataset)
        return dataset

# ---------------------------------------------------------------------------
# 股票名称 & PE 快照
# ---------------------------------------------------------------------------


def _stock_names_path() -> Path:
    return repo.repository_path()


def _pe_snapshot_path() -> Path:
    return repo.repository_path()


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
    path = repo.repository_path()

    with _CACHE_LOCK:
        if not refresh and repo.names_row_count() > 0:
            return repo.load_names()

        dataset = pl.from_pandas(_fetch_stock_names())
        repo.replace_names(dataset)
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

    return pl.DataFrame(rows)


def load_pe_snapshot(*, refresh: bool = False) -> pl.DataFrame:
    """加载 ``symbol / pe_ratio`` 快照（只读本地，不自动联网拉取）。"""
    path = repo.repository_path()

    with _CACHE_LOCK:
        if not refresh and repo.pe_row_count() > 0:
            return repo.load_pe()
        try:
            snapshot = _build_pe_snapshot(max_workers=get_tushare_max_workers())
            repo.replace_pe(snapshot)
            return snapshot
        except Exception as exc:  # noqa: BLE001
            if repo.pe_row_count() > 0:
                LOGGER.warning("rebuild pe snapshot failed, reusing stale cache: %s", exc)
                return repo.load_pe()
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
    path = repo.repository_path()
    existing = repo.load_names()
    rows_before = existing.height
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
    repo.upsert_names(fresh)
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
    path = repo.repository_path()
    stock_universe = [symbol for symbol in universe if _is_stock_symbol(symbol)]
    if not stock_universe:
        raise RuntimeError("empty stock universe — cannot build incremental pe snapshot")

    rows_before = 0
    targets: list[str]
    if repo.pe_row_count() > 0:
        existing = repo.load_pe()
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
    repo.upsert_pe(updates)
    return merged, {
        "rows_before": rows_before,
        "rows_after": merged.height,
        "updated_symbols": updates.height,
        "path": str(path),
    }


def _incremental_fetch_daily_bars(
    symbols: list[str],
    *,
    latest_dates: dict[str, datetime],
    max_workers: int,
    log_tag: str = "增量日线",
    coverage: tuple[date, date] | None = None,
    symbol_bounds: dict[str, tuple[date, date] | None] | None = None,
) -> tuple[list[pd.DataFrame], list[str], list[str]]:
    """对给定代码列表并发拉 Tushare 增量日线；不写库。返回 (frames, failed_symbols, refreshed_symbols)。

    ``coverage`` + ``symbol_bounds``：按回测区间补左侧历史或右侧更新（本地已有 last 时不再只拉末段）。
    """
    if not symbols:
        return [], [], []
    history_days = get_daily_history_days()
    end_date = datetime.now()
    fallback_start = end_date - timedelta(days=history_days)
    fallback_start_date = fallback_start.date()
    end_date_str = end_date.strftime("%Y%m%d")

    if coverage is not None:
        if symbol_bounds is None:
            raise ValueError("symbol_bounds is required when coverage is set")
        cov_start, cov_end = coverage
        end_req_clamped = min(cov_end, end_date.date())
        fetch_tasks: list[tuple[str, str, str]] = []
        for symbol in symbols:
            b = symbol_bounds[symbol]
            if b is None:
                start_date_eff = max(fallback_start_date, cov_start)
                end_date_eff = end_req_clamped
            else:
                dmin, dmax = b
                need_left = dmin > cov_start
                need_right = dmax < end_req_clamped
                if not need_left and not need_right:
                    continue
                if need_left and need_right:
                    start_date_eff = max(fallback_start_date, cov_start)
                    end_date_eff = end_req_clamped
                elif need_left:
                    start_date_eff = max(fallback_start_date, cov_start)
                    end_date_eff = dmin
                else:
                    start_date_eff = dmax - timedelta(days=INCREMENTAL_OVERLAP_DAYS)
                    end_date_eff = end_req_clamped
            if start_date_eff > end_date_eff:
                LOGGER.warning(
                    "%s: skip %s empty fetch window [%s, %s]",
                    log_tag,
                    symbol,
                    start_date_eff,
                    end_date_eff,
                )
                continue
            fetch_tasks.append(
                (
                    symbol,
                    start_date_eff.strftime("%Y%m%d"),
                    end_date_eff.strftime("%Y%m%d"),
                )
            )
        total_daily_tasks = len(fetch_tasks)
        if total_daily_tasks == 0:
            return [], [], []
        frames: list[pd.DataFrame] = []
        failed: list[str] = []
        refreshed_symbols: list[str] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    fetch_daily_one,
                    sym,
                    s_str,
                    e_str,
                    adjust="qfq",
                ): sym
                for sym, s_str, e_str in fetch_tasks
            }
            for future in as_completed(future_map):
                symbol = future_map[future]
                try:
                    frame = future.result()
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("incremental daily fetch failed for %s: %s", symbol, exc)
                    failed.append(symbol)
                else:
                    if not frame.empty:
                        frames.append(frame)
                        refreshed_symbols.append(symbol)
        return frames, failed, refreshed_symbols

    frames: list[pd.DataFrame] = []
    failed: list[str] = []
    refreshed_symbols: list[str] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {}
        for symbol in symbols:
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
            else:
                if not frame.empty:
                    frames.append(frame)
                    refreshed_symbols.append(symbol)

    return frames, failed, refreshed_symbols


def incremental_daily_for_symbols(
    symbols: Iterable[str],
    *,
    coverage: tuple[date, date] | None = None,
    symbol_bounds: dict[str, tuple[date, date] | None] | None = None,
) -> dict[str, object]:
    """仅更新指定代码的增量日线并写入 DuckDB；不刷新证券简称与 PE。

    供回测在本地缺数时按需补拉，避免 ``refresh_market_data(incremental)`` 对全市场扫一遍导致极慢。

    ``coverage`` 为 ``(start, end)`` 且提供 ``symbol_bounds`` 时：按该区间向左/向右补历史（仍受
    ``DDTRADING_DAILY_HISTORY_DAYS`` 限制，过早起始日会被裁到可拉取窗口）。
    """
    uniq = list(dict.fromkeys(_normalize_symbol(s) for s in symbols))
    if not uniq:
        return {"symbols_requested": 0, "updated_symbols": 0, "failed_symbols": []}

    if coverage is not None:
        if symbol_bounds is None:
            raise ValueError("symbol_bounds is required when coverage is set")
        missing = [s for s in uniq if s not in symbol_bounds]
        if missing:
            raise ValueError(f"symbol_bounds missing keys for symbols: {missing}")
        cov_start, cov_end = coverage
        today = datetime.now().date()
        end_clamped = min(cov_end, today)
        already_full = True
        for s in uniq:
            b = symbol_bounds[s]
            if b is None:
                already_full = False
                break
            dmin, dmax = b
            if dmin > cov_start or dmax < end_clamped:
                already_full = False
                break
        if already_full:
            return {
                "symbols_requested": len(uniq),
                "updated_symbols": 0,
                "failed_symbols": [],
                "skipped": True,
                "reason": "coverage_already_cached",
            }

    max_workers = get_tushare_max_workers()
    with _CACHE_LOCK:
        latest_dates = repo.get_last_daily_dates()
        frames, failed, refreshed = _incremental_fetch_daily_bars(
            uniq,
            latest_dates=latest_dates,
            max_workers=max_workers,
            log_tag="回测补数日线",
            coverage=coverage,
            symbol_bounds=symbol_bounds,
        )
        if frames:
            updates = pl.from_pandas(
                pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"])
            )
            repo.upsert_daily(updates)
    return {
        "symbols_requested": len(uniq),
        "updated_symbols": len(set(refreshed)),
        "failed_symbols": failed,
    }


def _refresh_market_data_incremental() -> dict[str, object]:
    path = repo.repository_path()
    max_workers = get_tushare_max_workers()
    universe = list_universe()

    with _CACHE_LOCK:
        existing = repo.load_daily()
        rows_before = existing.height
        latest_dates = repo.get_last_daily_dates()

        frames, failed, refreshed_symbols = _incremental_fetch_daily_bars(
            universe,
            latest_dates=latest_dates,
            max_workers=max_workers,
            log_tag="增量刷新",
        )

        if frames:
            updates = pl.from_pandas(
                pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"])
            )
            daily = _merge_daily_frames(existing, updates)
            repo.upsert_daily(updates)
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

    ``mode='full'``: 全量重建 daily / names / pe 三张 DuckDB 表。
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
            "path": str(repo.repository_path()),
        },
        "names": {
            "rows": names.height,
            "path": str(repo.repository_path()),
        },
        "pe": {
            "status": "skipped",
            "reason": "auto PE refresh disabled",
            "path": str(repo.repository_path()),
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
    del symbol
    return repo.upsert_daily(new_daily)


def _upsert_pe(symbol: str, pe_value: float) -> None:
    row = pl.DataFrame(
        {
            "symbol": [symbol],
            "pe_ratio": [pe_value],
            "updated_at": [datetime.now().isoformat(timespec="seconds")],
        }
    )
    repo.upsert_pe(row)


def _upsert_name(symbol: str, name: str) -> None:
    row = pl.DataFrame({"symbol": [symbol], "name": [name]})
    repo.upsert_names(row)


def ensure_symbol_cached(
    symbol: str,
    *,
    days: int = 365,
    adjust: str = "qfq",
) -> dict[str, object]:
    """按需把单只股票的 daily / 名称增量写入本地 DuckDB 缓存。

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
    """仅刷新日线 DuckDB 缓存（不触发 PE/名称刷新）。"""
    dataset = load_tushare_daily(refresh=True)
    return {
        "rows": dataset.height,
        "symbols": dataset.select(pl.col("symbol").n_unique()).item(),
        "path": str(repo.repository_path()),
    }
