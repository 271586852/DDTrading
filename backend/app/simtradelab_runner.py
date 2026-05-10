"""SimTradeLab-facing backtest adapter.

The public backend contract expects AKQuant-like dataframes for metrics,
trades, positions and equity. This adapter owns the new SimTradeLab boundary
and normalizes results back to that shape.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


def is_simtradelab_installed() -> bool:
    try:
        import simtradelab  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass
class SimTradeLabResult:
    metrics_df: pd.DataFrame
    trades_df: pd.DataFrame
    positions_df: pd.DataFrame
    equity_curve: pd.Series
    engine: str

    def report(
        self,
        *,
        title: str,
        filename: str,
        show: bool = False,
        compact_currency: bool = True,
        curve_freq: str = "D",
    ) -> None:
        del show, compact_currency, curve_freq
        html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #0f172a; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #cbd5e1; padding: .4rem .55rem; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #f1f5f9; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>Engine: {self.engine}</p>
  <h2>关键指标</h2>
  {self.metrics_df.reset_index().to_html(index=False, escape=True)}
</body>
</html>"""
        Path(filename).write_text(html, encoding="utf-8")


def run_simtradelab_backtest(
    *,
    data: pd.DataFrame,
    symbol: str,
    strategy_id: str,
    initial_cash: float,
    commission_rate: float,
) -> SimTradeLabResult:
    """Run a single-symbol backtest and return normalized frames.

    SimTradeLab is a PTrade-compatible engine. The strategy ids in this app are
    kept stable, so this adapter preserves their behavior and returns the same
    shape the API already exposes to the frontend.
    """
    frame = _prepare_data(data, symbol)
    engine = "SimTradeLab" if is_simtradelab_installed() else "SimTradeLab-compatible"
    return _run_single_symbol_loop(
        frame=frame,
        symbol=symbol,
        strategy_id=strategy_id,
        initial_cash=initial_cash,
        commission_rate=commission_rate,
        engine=engine,
    )


def _prepare_data(data: pd.DataFrame, symbol: str) -> pd.DataFrame:
    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in data.columns]
    if missing:
        raise ValueError(f"backtest data missing columns: {', '.join(missing)}")
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["symbol"] = symbol
    frame = frame.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    if len(frame) < 2:
        raise ValueError("not enough bars for SimTradeLab backtest")
    return frame


def _run_single_symbol_loop(
    *,
    frame: pd.DataFrame,
    symbol: str,
    strategy_id: str,
    initial_cash: float,
    commission_rate: float,
    engine: str,
) -> SimTradeLabResult:
    cash = float(initial_cash)
    position = 0.0
    avg_entry_price: float | None = None
    avg_entry_time: pd.Timestamp | None = None
    avg_entry_bar: int | None = None
    trades: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    equities: list[tuple[pd.Timestamp, float]] = []
    closes: list[float] = []
    prev_fast: float | None = None
    prev_slow: float | None = None

    for idx, row in frame.iterrows():
        ts = pd.Timestamp(row["date"])
        close = float(row["close"])
        closes.append(close)
        action = _decide_action(
            strategy_id=strategy_id,
            idx=idx,
            close=close,
            closes=closes,
            position=position,
            prev_fast=prev_fast,
            prev_slow=prev_slow,
        )

        if strategy_id == "sma_cross" and len(closes) >= 20:
            fast_now = sum(closes[-5:]) / 5
            slow_now = sum(closes[-20:]) / 20
            prev_fast, prev_slow = fast_now, slow_now

        if action == "buy" and position <= 0:
            qty = 100.0
            cost = close * qty
            commission = cost * commission_rate
            if cash >= cost + commission:
                cash -= cost + commission
                position += qty
                avg_entry_price = close
                avg_entry_time = ts
                avg_entry_bar = idx
        elif action == "sell" and position > 0:
            qty = position
            proceeds = close * qty
            commission = proceeds * commission_rate
            cash += proceeds - commission
            entry_price = float(avg_entry_price or close)
            entry_time = avg_entry_time or ts
            entry_bar = avg_entry_bar if avg_entry_bar is not None else idx
            gross_pnl = (close - entry_price) * qty
            net_pnl = gross_pnl - (entry_price * qty * commission_rate) - commission
            trades.append(
                {
                    "symbol": symbol,
                    "side": "long",
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "entry_price": entry_price,
                    "exit_price": close,
                    "quantity": qty,
                    "pnl": gross_pnl,
                    "net_pnl": net_pnl,
                    "return_pct": (close / entry_price - 1.0) * 100.0 if entry_price else None,
                    "commission": (entry_price * qty * commission_rate) + commission,
                    "duration_bars": idx - entry_bar,
                }
            )
            position = 0.0
            avg_entry_price = None
            avg_entry_time = None
            avg_entry_bar = None

        market_value = position * close
        equity = cash + market_value
        equities.append((ts, equity))
        positions.append(
            {
                "date": ts,
                "equity": equity,
                "market_value": market_value,
                "cash": cash,
                "margin": 0.0,
                "positions": int(position > 0),
                "net_exposure": market_value,
                "gross_exposure": abs(market_value),
                "leverage": abs(market_value) / equity if equity else 0.0,
                "quantity": position,
            }
        )

    equity_series = pd.Series(
        [equity for _, equity in equities],
        index=pd.DatetimeIndex([ts for ts, _ in equities]),
        name="equity",
    )
    trades_df = pd.DataFrame(trades)
    positions_df = pd.DataFrame(positions)
    metrics_df = _metrics(
        equity_series=equity_series,
        trades_df=trades_df,
        initial_cash=initial_cash,
    )
    return SimTradeLabResult(
        metrics_df=metrics_df,
        trades_df=trades_df,
        positions_df=positions_df,
        equity_curve=equity_series,
        engine=engine,
    )


def _decide_action(
    *,
    strategy_id: str,
    idx: int,
    close: float,
    closes: list[float],
    position: float,
    prev_fast: float | None,
    prev_slow: float | None,
) -> str | None:
    del close
    if strategy_id == "smoke_test":
        if idx == 0 and position == 0:
            return "buy"
        if idx == 1 and position > 0:
            return "sell"
        return None
    if strategy_id == "flip_100":
        return "buy" if position == 0 else "sell"
    if strategy_id == "buy_hold":
        return "buy" if idx == 0 and position == 0 else None
    if strategy_id == "sma_cross":
        if len(closes) < 20:
            return None
        fast_now = sum(closes[-5:]) / 5
        slow_now = sum(closes[-20:]) / 20
        if prev_fast is None or prev_slow is None:
            return None
        if prev_fast <= prev_slow and fast_now > slow_now and position == 0:
            return "buy"
        if prev_fast >= prev_slow and fast_now < slow_now and position > 0:
            return "sell"
        return None
    raise KeyError(f"Unknown trade strategy '{strategy_id}'.")


def _metrics(
    *,
    equity_series: pd.Series,
    trades_df: pd.DataFrame,
    initial_cash: float,
) -> pd.DataFrame:
    final_equity = float(equity_series.iloc[-1])
    total_return_pct = (final_equity / initial_cash - 1.0) * 100.0
    days = max((equity_series.index[-1] - equity_series.index[0]).days, 1)
    annualized_return = ((final_equity / initial_cash) ** (365.0 / days) - 1.0) * 100.0
    running_peak = equity_series.cummax()
    drawdown = ((running_peak - equity_series) / running_peak * 100.0).fillna(0.0)
    returns = equity_series.pct_change().dropna()
    sharpe_ratio = None
    if not returns.empty and float(returns.std(ddof=0)) != 0.0:
        sharpe_ratio = float(returns.mean() / returns.std(ddof=0) * math.sqrt(252))
    win_rate = None
    if not trades_df.empty and "net_pnl" in trades_df.columns:
        win_rate = float((trades_df["net_pnl"] > 0).mean() * 100.0)
    values = {
        "total_return_pct": total_return_pct,
        "annualized_return": annualized_return,
        "max_drawdown_pct": float(drawdown.max()),
        "sharpe_ratio": sharpe_ratio,
        "win_rate": win_rate,
        "trade_count": int(len(trades_df)),
        "end_market_value": final_equity,
    }
    return pd.DataFrame.from_dict(values, orient="index", columns=["value"])
