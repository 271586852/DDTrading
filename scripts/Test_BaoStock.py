from __future__ import annotations

from datetime import datetime, timedelta

import baostock as bs
import pandas as pd


SYMBOLS = ("600519","601958","600726")


def to_baostock_code(symbol: str) -> str:
    code = symbol.strip()[-6:].zfill(6)
    if code.startswith(("0", "1", "2", "3")):
        return f"sz.{code}"
    return f"sh.{code}"


def query_daily(symbol: str) -> None:
    end_date = datetime.now()
    start_date = end_date - timedelta(days=3650)
    bs_code = to_baostock_code(symbol)

    print(f"\n=== {symbol} ({bs_code}) ===")
    rs = bs.query_history_k_data_plus(
        bs_code,
        fields="date,code,open,high,low,close,volume,amount,tradestatus",
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        frequency="d",
        adjustflag="2",
    )
    print(f"error_code={rs.error_code!r}, error_msg={rs.error_msg!r}")

    rows: list[list[str]] = []
    while rs.next():
        rows.append(rs.get_row_data())

    print(f"rows={len(rows)}")
    if not rows:
        return

    frame = pd.DataFrame(rows, columns=rs.fields)
    print("head:")
    print(frame.head(3).to_string(index=False))
    print("tail:")
    print(frame.tail(3).to_string(index=False))


def main() -> None:
    login = bs.login()
    print(f"login: error_code={login.error_code!r}, error_msg={login.error_msg!r}")
    if login.error_code != "0":
        return

    try:
        for symbol in SYMBOLS:
            query_daily(symbol)
    finally:
        logout = bs.logout()
        print(f"\nlogout: error_code={logout.error_code!r}, error_msg={logout.error_msg!r}")


if __name__ == "__main__":
    main()
