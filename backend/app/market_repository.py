"""DuckDB-backed market data repository.

This module is the persistence boundary for local market data. Tushare remains
the online source; DuckDB owns cached daily bars, names, PE snapshots and cache
revision metadata.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from pathlib import Path
from threading import RLock
from typing import Any

import pandas as pd
import polars as pl

from app.config import get_market_duckdb_path

try:
    import duckdb
except ImportError:  # pragma: no cover - dependency guard
    duckdb = None  # type: ignore[assignment]


DAILY_SCHEMA = {
    "date": pl.Datetime,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "symbol": pl.Utf8,
}
NAMES_SCHEMA = {"symbol": pl.Utf8, "name": pl.Utf8}
PE_SCHEMA = {"symbol": pl.Utf8, "pe_ratio": pl.Float64, "updated_at": pl.Utf8}

_DB_LOCK = RLock()


def _empty_daily() -> pl.DataFrame:
    return pl.DataFrame(schema=DAILY_SCHEMA)


def _empty_names() -> pl.DataFrame:
    return pl.DataFrame(schema=NAMES_SCHEMA)


def _empty_pe() -> pl.DataFrame:
    return pl.DataFrame(schema=PE_SCHEMA)


def _db_path() -> Path:
    path = get_market_duckdb_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect():
    if duckdb is None:
        raise ModuleNotFoundError("duckdb is not installed")
    con = duckdb.connect(str(_db_path()))
    _init_schema(con)
    return con


def _init_schema(con: Any) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_bars (
            symbol VARCHAR NOT NULL,
            date TIMESTAMP NOT NULL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            PRIMARY KEY (symbol, date)
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS stock_names (
            symbol VARCHAR PRIMARY KEY,
            name VARCHAR,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pe_snapshot (
            symbol VARCHAR PRIMARY KEY,
            pe_ratio DOUBLE,
            trade_date DATE,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS cache_meta (
            key VARCHAR PRIMARY KEY,
            value VARCHAR,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def repository_path() -> Path:
    return _db_path()


def has_daily_data() -> bool:
    with _DB_LOCK, _connect() as con:
        count = con.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
    return int(count or 0) > 0


def load_daily() -> pl.DataFrame:
    with _DB_LOCK, _connect() as con:
        pdf = con.execute(
            """
            SELECT date, open, high, low, close, volume, symbol
            FROM daily_bars
            ORDER BY symbol, date
            """
        ).fetchdf()
    if pdf.empty:
        return _empty_daily()
    pdf["date"] = pd.to_datetime(pdf["date"], errors="coerce")
    return pl.from_pandas(pdf).select(list(DAILY_SCHEMA.keys()))


def load_daily_for_symbol(
    symbol: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> pl.DataFrame:
    clauses = ["symbol = ?"]
    params: list[Any] = [symbol]
    if start is not None:
        clauses.append("date >= ?")
        params.append(start)
    if end is not None:
        clauses.append("date <= ?")
        params.append(end)
    where_sql = " AND ".join(clauses)
    with _DB_LOCK, _connect() as con:
        pdf = con.execute(
            f"""
            SELECT date, open, high, low, close, volume, symbol
            FROM daily_bars
            WHERE {where_sql}
            ORDER BY date
            """,
            params,
        ).fetchdf()
    if pdf.empty:
        return _empty_daily()
    pdf["date"] = pd.to_datetime(pdf["date"], errors="coerce")
    return pl.from_pandas(pdf).select(list(DAILY_SCHEMA.keys()))


def replace_daily(frame: pl.DataFrame) -> None:
    pdf = frame.select(list(DAILY_SCHEMA.keys())).to_pandas()
    with _DB_LOCK, _connect() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM daily_bars")
            if not pdf.empty:
                con.register("daily_updates", pdf)
                con.execute(
                    """
                    INSERT INTO daily_bars
                    SELECT symbol, date, open, high, low, close, volume
                    FROM daily_updates
                    """
                )
                con.unregister("daily_updates")
            _touch_revision(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def upsert_daily(frame: pl.DataFrame) -> int:
    if frame.height == 0:
        return 0
    pdf = frame.select(list(DAILY_SCHEMA.keys())).to_pandas()
    with _DB_LOCK, _connect() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.register("daily_updates", pdf)
            con.execute(
                """
                DELETE FROM daily_bars
                USING daily_updates
                WHERE daily_bars.symbol = daily_updates.symbol
                  AND daily_bars.date = daily_updates.date
                """
            )
            con.execute(
                """
                INSERT INTO daily_bars
                SELECT symbol, date, open, high, low, close, volume
                FROM daily_updates
                """
            )
            con.unregister("daily_updates")
            _touch_revision(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return frame.height


def load_names() -> pl.DataFrame:
    with _DB_LOCK, _connect() as con:
        pdf = con.execute(
            "SELECT symbol, name FROM stock_names ORDER BY symbol"
        ).fetchdf()
    if pdf.empty:
        return _empty_names()
    return pl.from_pandas(pdf).select(["symbol", "name"])


def replace_names(frame: pl.DataFrame) -> None:
    with _DB_LOCK, _connect() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM stock_names")
            _insert_names(con, frame)
            _touch_revision(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def upsert_names(frame: pl.DataFrame) -> int:
    if frame.height == 0:
        return 0
    with _DB_LOCK, _connect() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            _delete_by_symbols(con, "stock_names", frame.get_column("symbol").to_list())
            _insert_names(con, frame)
            _touch_revision(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return frame.height


def _insert_names(con: Any, frame: pl.DataFrame) -> None:
    pdf = frame.select(["symbol", "name"]).to_pandas()
    if pdf.empty:
        return
    con.register("name_updates", pdf)
    con.execute(
        """
        INSERT INTO stock_names (symbol, name, updated_at)
        SELECT symbol, name, CURRENT_TIMESTAMP
        FROM name_updates
        """
    )
    con.unregister("name_updates")


def load_pe() -> pl.DataFrame:
    with _DB_LOCK, _connect() as con:
        pdf = con.execute(
            """
            SELECT symbol, pe_ratio, CAST(updated_at AS VARCHAR) AS updated_at
            FROM pe_snapshot
            ORDER BY symbol
            """
        ).fetchdf()
    if pdf.empty:
        return _empty_pe()
    return pl.from_pandas(pdf).select(["symbol", "pe_ratio", "updated_at"])


def replace_pe(frame: pl.DataFrame) -> None:
    with _DB_LOCK, _connect() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM pe_snapshot")
            _insert_pe(con, frame)
            _touch_revision(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def upsert_pe(frame: pl.DataFrame) -> int:
    if frame.height == 0:
        return 0
    with _DB_LOCK, _connect() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            _delete_by_symbols(con, "pe_snapshot", frame.get_column("symbol").to_list())
            _insert_pe(con, frame)
            _touch_revision(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return frame.height


def _insert_pe(con: Any, frame: pl.DataFrame) -> None:
    cols = ["symbol", "pe_ratio"]
    pdf = frame.select(cols).to_pandas()
    if pdf.empty:
        return
    con.register("pe_updates", pdf)
    con.execute(
        """
        INSERT INTO pe_snapshot (symbol, pe_ratio, updated_at)
        SELECT symbol, pe_ratio, CURRENT_TIMESTAMP
        FROM pe_updates
        """
    )
    con.unregister("pe_updates")


def _delete_by_symbols(con: Any, table: str, symbols: list[str]) -> None:
    if not symbols:
        return
    pdf = pd.DataFrame({"symbol": symbols})
    con.register("delete_symbols", pdf)
    con.execute(
        f"DELETE FROM {table} USING delete_symbols WHERE {table}.symbol = delete_symbols.symbol"
    )
    con.unregister("delete_symbols")


def get_last_daily_dates() -> dict[str, datetime]:
    with _DB_LOCK, _connect() as con:
        pdf = con.execute(
            """
            SELECT symbol, MAX(date) AS last_date
            FROM daily_bars
            GROUP BY symbol
            """
        ).fetchdf()
    out: dict[str, datetime] = {}
    for row in pdf.to_dict(orient="records"):
        value = row.get("last_date")
        if value is None or pd.isna(value):
            continue
        out[str(row["symbol"])] = pd.Timestamp(value).to_pydatetime()
    return out


def daily_row_count() -> int:
    with _DB_LOCK, _connect() as con:
        count = con.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0]
    return int(count or 0)


def names_row_count() -> int:
    with _DB_LOCK, _connect() as con:
        count = con.execute("SELECT COUNT(*) FROM stock_names").fetchone()[0]
    return int(count or 0)


def pe_row_count() -> int:
    with _DB_LOCK, _connect() as con:
        count = con.execute("SELECT COUNT(*) FROM pe_snapshot").fetchone()[0]
    return int(count or 0)


def mark_market_refresh() -> None:
    with _DB_LOCK, _connect() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            _set_meta(con, "market_refresh_unix", str(time.time()))
            _touch_revision(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise


def read_market_refresh_unix() -> float | None:
    value = _read_meta("market_refresh_unix")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def cache_revision() -> float:
    values = [read_market_refresh_unix() or 0.0]
    value = _read_meta("cache_revision_unix")
    if value is not None:
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            pass
    path = repository_path()
    if path.is_file():
        values.append(path.stat().st_mtime)
    return float(max(values))


def _read_meta(key: str) -> str | None:
    with _DB_LOCK, _connect() as con:
        row = con.execute("SELECT value FROM cache_meta WHERE key = ?", [key]).fetchone()
    if row is None:
        return None
    return str(row[0])


def _set_meta(con: Any, key: str, value: str) -> None:
    con.execute("DELETE FROM cache_meta WHERE key = ?", [key])
    con.execute(
        "INSERT INTO cache_meta (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
        [key, value],
    )


def _touch_revision(con: Any) -> None:
    _set_meta(con, "cache_revision_unix", str(time.time()))
