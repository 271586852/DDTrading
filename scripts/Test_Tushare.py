"""Simple Tushare connectivity/data test script.

Usage:
  python scripts/Test_Tushare.py --token <YOUR_TOKEN>
  python scripts/Test_Tushare.py --ts-code 000001.SZ --start 20250101 --end 20250430

Or set env var first:
  $env:TUSHARE_TOKEN="your_token"   # PowerShell
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import tushare as ts
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "tushare is not installed. Run: python -m pip install tushare"
    ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Tushare daily API")
    parser.add_argument("--token", default=None, help="Tushare token")
    parser.add_argument("--ts-code", default="000001.SZ", help="e.g. 000001.SZ")
    parser.add_argument("--start", default="20250101", help="YYYYMMDD")
    parser.add_argument("--end", default="20250430", help="YYYYMMDD")
    parser.add_argument(
        "--output",
        default="scripts/output/tushare_daily_test.csv",
        help="Output CSV path",
    )
    return parser.parse_args()


def resolve_token(cli_token: Optional[str]) -> str:
    token = (cli_token or os.getenv("TUSHARE_TOKEN", "")).strip()
    if not token:
        raise SystemExit(
            "Missing Tushare token. Use --token or set TUSHARE_TOKEN env var."
        )
    return token


def main() -> None:
    args = parse_args()
    token = resolve_token(args.token)

    ts.set_token(token)
    pro = ts.pro_api()

    print("Requesting daily data from Tushare...")
    df = pro.daily(ts_code=args.ts_code, start_date=args.start, end_date=args.end)

    if df is None or df.empty:
        print("No data returned.")
        return

    # Sort by trade date ascending for readability.
    df = df.sort_values("trade_date").reset_index(drop=True)

    print(f"Fetched rows: {len(df)}")
    print("Columns:", list(df.columns))
    print("\nHead:")
    print(df.head(5).to_string(index=False))
    print("\nTail:")
    print(df.tail(5).to_string(index=False))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"\nSaved CSV: {out_path.resolve()}")

    # Optional quick check for required OHLCV-like columns.
    expected = {"trade_date", "open", "high", "low", "close", "vol"}
    missing = expected - set(df.columns)
    if missing:
        print(f"Warning: missing expected columns: {sorted(missing)}")
    else:
        print("Column check passed (trade_date/open/high/low/close/vol).")


if __name__ == "__main__":
    main()
