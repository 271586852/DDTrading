# -*- coding: utf-8 -*-
"""
使用 akshare 拉取真实 A 股历史行情，并通过 akquant 进行回测。

数据源策略（按顺序尝试，失败自动切换下一个）：
    1) 腾讯财经      ak.stock_zh_a_hist_tx      （域名: web.ifzq.gtimg.cn）
    2) 新浪财经      ak.stock_zh_a_daily        （域名: finance.sina.com.cn）
    3) 东方财富      ak.stock_zh_a_hist         （域名: push2his.eastmoney.com）

akquant 所需字段：date / open / high / low / close / volume / symbol
"""

import os
import sys

# --- Windows 控制台中文乱码修复 ---
# 1) 把 Python 的 stdout/stderr 强制设为 utf-8
# 2) 把 Windows 控制台代码页切到 65001(UTF-8)，
#    避免 PowerShell / cmd / code-runner 按 GBK 解码导致中文乱码
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass


# --- 网络预处理：避免被系统代理拦截 & 伪装成浏览器请求头 ---
for _key in [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]:
    os.environ.pop(_key, None)

import requests

_BROWSER_LIKE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "keep-alive",
}

_OriginalSession = requests.Session


class _NoProxyBrowserSession(_OriginalSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.trust_env = False
        self.proxies = {}
        self.headers.update(_BROWSER_LIKE_HEADERS)


requests.Session = _NoProxyBrowserSession
requests.sessions.Session = _NoProxyBrowserSession

# --- 正式业务导入 ---
import pandas as pd
import akshare as ak
from akquant import Strategy, run_backtest


# ============================================================
# 数据源适配
# ============================================================

REQUIRED_COLS = ["date", "open", "high", "low", "close", "volume", "symbol"]


def _with_market_prefix(symbol: str) -> str:
    """新浪接口需要带市场前缀，例如 sh600000 / sz000001 / bj430047"""
    s = symbol.zfill(6)
    if s.startswith(("5", "6", "9", "11", "13")):
        return f"sh{s}"
    if s.startswith(("0", "2", "3")):
        return f"sz{s}"
    if s.startswith(("4", "8")):
        return f"bj{s}"
    return f"sh{s}"


def _normalize(
    df: pd.DataFrame,
    *,
    symbol: str,
    column_mapping: dict,
) -> pd.DataFrame:
    missing = [c for c in column_mapping if c not in df.columns]
    if missing:
        raise RuntimeError(
            f"返回的列缺失: {missing}, 实际列: {list(df.columns)}"
        )

    out = df[list(column_mapping.keys())].rename(columns=column_mapping).copy()
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


def _fetch_sina(symbol: str, start_date: str, end_date: str, adjust: str) -> pd.DataFrame:
    sina_symbol = _with_market_prefix(symbol)
    raw = ak.stock_zh_a_daily(
        symbol=sina_symbol,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust if adjust else "",
    )
    if raw is None or raw.empty:
        raise RuntimeError("新浪返回空数据")

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


def _fetch_tencent(symbol: str, start_date: str, end_date: str, adjust: str) -> pd.DataFrame:
    tx_symbol = _with_market_prefix(symbol)
    raw = ak.stock_zh_a_hist_tx(
        symbol=tx_symbol,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust if adjust else "",
    )
    if raw is None or raw.empty:
        raise RuntimeError("腾讯返回空数据")

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


def _fetch_eastmoney(symbol: str, start_date: str, end_date: str, adjust: str) -> pd.DataFrame:
    raw = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start_date,
        end_date=end_date,
        adjust=adjust if adjust else "",
    )
    if raw is None or raw.empty:
        raise RuntimeError("东方财富返回空数据")

    return _normalize(
        raw,
        symbol=symbol,
        column_mapping={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        },
    )


DATA_SOURCES = [
    ("tencent", _fetch_tencent),
    ("sina", _fetch_sina),
    ("eastmoney", _fetch_eastmoney),
]


def fetch_data(
    symbol: str = "600000",
    start_date: str = "20230101",
    end_date: str = "20231231",
    adjust: str = "qfq",
) -> pd.DataFrame:
    """按顺序尝试多个数据源，任意一个成功即返回。"""
    errors: list[str] = []
    for name, fetcher in DATA_SOURCES:
        try:
            print(f"  - 尝试数据源: {name} ...")
            df = fetcher(symbol, start_date, end_date, adjust)
            print(f"  - [成功] 来源: {name}, 行数: {len(df)}")
            return df
        except Exception as exc:  # noqa: BLE001
            msg = f"{name} 失败: {exc!r}"
            print(f"  - {msg}")
            errors.append(msg)

    raise RuntimeError("所有数据源均失败:\n" + "\n".join(errors))


# ============================================================
# 策略 & 回测入口
# ============================================================


class MyStrategy(Strategy):
    def on_bar(self, bar):
        position = self.get_position(bar.symbol)
        if position == 0:
            self.buy(symbol=bar.symbol, quantity=100)
        elif position > 0:
            self.sell(symbol=bar.symbol, quantity=100)


def main() -> None:
    target_symbol = "600000"

    print(f"正在拉取 {target_symbol} 的历史行情 (多源 fallback) ...")
    try:
        df = fetch_data(symbol=target_symbol)
    except Exception as exc:  # noqa: BLE001
        print(f"[失败] 拉取数据失败: {exc!r}")
        sys.exit(1)

    print(
        f"[成功] 共 {len(df)} 条，时间范围：{df['date'].min()} ~ {df['date'].max()}"
    )
    print(df.head().to_string(index=False))

    result = run_backtest(
        strategy=MyStrategy,
        data=df,
        symbols=target_symbol,
        initial_cash=500_000.0,
        commission_rate=0.0003,
    )

    print(f"\nTotal Return: {result.metrics.total_return_pct:.2f}%")
    print(f"Sharpe Ratio: {result.metrics.sharpe_ratio:.2f}")
    print(f"Max Drawdown: {result.metrics.max_drawdown_pct:.2f}%")

    print("\n--- 绩效指标 ---")
    print(result.metrics_df)
    print("\n--- 交易记录 ---")
    print(result.trades_df)
    print("\n--- 每日持仓 ---")
    print(result.positions_df)


if __name__ == "__main__":
    main()
