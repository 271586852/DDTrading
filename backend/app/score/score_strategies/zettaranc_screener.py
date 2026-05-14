"""选股与择时（DuckDB / Polars 日线链路；无 SQLite）。

使用 ``daily_data_list_from_polars`` 将 Polars 日线转为 ``List[DailyData]``，
再调用 ``analyze_screener_stock(ts_code, daily_klines, name=...)``。
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import polars as pl

from app.common.indicators import DailyData, bar_dict_rows_from_daily_data
from app.common.market_data import _to_ts_code


def _trade_date_str(v: Any) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y%m%d")
    return str(v)[:10].replace("-", "")


def daily_data_list_from_polars(
    df: pl.DataFrame,
    *,
    ts_code: str | None = None,
) -> List[DailyData]:
    """把 ``load_daily_for_symbol`` 等返回的日线 Polars 表转为 ``List[DailyData]``（升序）。

    期望列：``date, open, high, low, close, volume``；可选 ``amount``、``pct_chg``。
    """
    if df.height == 0:
        return []
    # 统一转成按日期升序的 DailyData，后面的指标函数都假设输入满足这个顺序。
    work = df.with_columns(
        pl.col("date").cast(pl.Datetime(time_unit="ns"), strict=False)
    ).sort("date")
    if ts_code is None:
        if "symbol" not in work.columns:
            raise ValueError("缺少 symbol 列时请显式传入 ts_code=")
        ts_code = _to_ts_code(str(work.get_column("symbol")[0]))

    dates = [_trade_date_str(x) for x in work.get_column("date").to_list()]
    opens = work.get_column("open").cast(pl.Float64).fill_null(0.0).to_list()
    highs = work.get_column("high").cast(pl.Float64).fill_null(0.0).to_list()
    lows = work.get_column("low").cast(pl.Float64).fill_null(0.0).to_list()
    closes = work.get_column("close").cast(pl.Float64).fill_null(0.0).to_list()
    vols = work.get_column("volume").cast(pl.Float64).fill_null(0.0).to_list()

    has_amount = "amount" in work.columns
    amounts = (
        work.get_column("amount").cast(pl.Float64).fill_null(0.0).to_list()
        if has_amount
        else None
    )
    has_pct = "pct_chg" in work.columns
    pcts_in = (
        work.get_column("pct_chg").cast(pl.Float64).fill_null(0.0).to_list()
        if has_pct
        else None
    )

    out: List[DailyData] = []
    for i in range(work.height):
        c = float(closes[i])
        v = float(vols[i])
        prev_close = float(closes[i - 1]) if i > 0 else c
        if has_pct and pcts_in is not None:
            pct = float(pcts_in[i])
        elif prev_close:
            pct = (c - prev_close) / prev_close * 100.0
        else:
            pct = 0.0
        if amounts is not None:
            amt = float(amounts[i])
        else:
            # 历史表未提供 amount 时，用成交量 * 收盘价兜底出近似成交额。
            amt = v * c
        out.append(
            DailyData(
                ts_code=ts_code,
                trade_date=str(dates[i]),
                open=float(opens[i]),
                high=float(highs[i]),
                low=float(lows[i]),
                close=c,
                vol=v,
                amount=amt,
                pct_chg=pct,
                prev_close=prev_close,
            )
        )
    return out


def _screener_bar_rows(ts_code: str, klines: List[DailyData]) -> List[Dict[str, Any]]:
    rows = bar_dict_rows_from_daily_data(klines)
    # 下游部分信号函数依赖 ts_code 字段，这里补齐成统一结构。
    for r in rows:
        r["ts_code"] = ts_code
    return rows


@dataclass
class StockScore:
    """股票评分"""
    ts_code: str
    name: str = ""
    score: float = 0           # 综合评分 0-100
    b1_score: float = 0        # B1买点评分
    trend_score: float = 0     # 趋势评分
    volume_score: float = 0     # 量价评分
    risk_score: float = 0      # 风险评分
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def rating(self) -> str:
        """评级"""
        if self.score >= 80:
            return "★★★★★ 强烈推荐"
        elif self.score >= 65:
            return "★★★★☆ 推荐"
        elif self.score >= 50:
            return "★★★☆☆ 可关注"
        elif self.score >= 35:
            return "★★☆☆☆ 谨慎"
        else:
            return "★☆☆☆☆ 不推荐"


@dataclass
class MarketStatus:
    """大盘状态"""
    trade_date: str
    is_trading: bool = True           # 是否可交易
    market_direction: str = "NEUTRAL"  # LONG/NEUTRAL/SHORT
    market_strength: float = 0        # 0-100
    reasons: List[str] = field(default_factory=list)


def calculate_ma(prices: List[float], period: int) -> float:
    """计算均线"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period


def calculate_vol_ma(vols: List[float], period: int) -> float:
    """计算量能均线"""
    if len(vols) < period:
        return 0
    return sum(vols[-period:]) / period


def calculate_kdj(klines: List[Dict], period: int = 9) -> Tuple[float, float, float]:
    """计算KDJ"""
    if len(klines) < period:
        return 50, 50, 50

    rsv_list = []
    # 先滚动计算 RSV，再按经典 KDJ 平滑公式递推 K / D / J。
    for i in range(period - 1, len(klines)):
        low_list = [klines[j]['low'] for j in range(i - period + 1, i + 1)]
        high_list = [klines[j]['high'] for j in range(i - period + 1, i + 1)]
        low_min = min(low_list)
        high_max = max(high_list)

        if high_max == low_min:
            rsv = 50
        else:
            rsv = (klines[i]['close'] - low_min) / (high_max - low_min) * 100
        rsv_list.append(rsv)

    k = d = 50.0
    for rsv in rsv_list:
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k

    j = 3 * k - 2 * d
    return round(k, 2), round(d, 2), round(j, 2)


def calculate_bbi(klines: List[Dict]) -> float:
    """计算BBI"""
    if len(klines) < 24:
        return 0
    closes = [k['close'] for k in klines]
    return round((calculate_ma(closes, 3) + calculate_ma(closes, 6) +
                 calculate_ma(closes, 12) + calculate_ma(closes, 24)) / 4, 2)


def is_perfect_pattern(klines: List[Dict]) -> Tuple[bool, List[str]]:
    """
    判断是否完美图形

    完美图形条件:
    1. BBI之上
    2. 缩量整理
    3. 均线多头（可选）
    4. 非高位
    """
    if len(klines) < 30:
        return False, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]
    vols = [k['vol'] for k in klines]

    reasons = []
    warnings = []

    # 1. BBI之上
    if today['close'] > bbi:
        reasons.append("价格在BBI之上")
    else:
        warnings.append("价格在BBI下方")

    # 2. 缩量整理
    ma5_vol = calculate_vol_ma(vols, 5)
    today_vol = today['vol']
    if today_vol < ma5_vol * 0.7:
        reasons.append("缩量整理")
    elif today_vol > ma5_vol * 1.5:
        warnings.append("放量突破，需观察")

    # 3. 均线多头
    ma5 = calculate_ma(closes, 5)
    ma10 = calculate_ma(closes, 10)
    ma20 = calculate_ma(closes, 20)
    if ma5 > ma10 > ma20:
        reasons.append("均线多头排列")
    elif ma5 < ma10:
        warnings.append("均线空头")

    # 4. 非高位（距历史高点跌幅充分）
    max_high = max(k['high'] for k in klines[-60:])
    drop_ratio = (max_high - today['close']) / max_high
    if drop_ratio > 0.3:
        reasons.append(f"相对高点回调{drop_ratio*100:.0f}%")
    elif drop_ratio < 0.1:
        warnings.append("接近历史高位")

    # 综合判断
    is_perfect = len(reasons) >= 2 and len(warnings) == 0

    return is_perfect, reasons


def score_b1_opportunity(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估B1买点机会

    返回: (评分0-100, 原因列表)
    """
    if len(klines) < 20:
        return 0, ["数据不足"]

    today = klines[-1]
    k, d, j = calculate_kdj(klines)
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]
    vols = [k['vol'] for k in klines]

    score = 0
    reasons = []

    # J值评分（核心）
    if j < -15:
        score += 35
        reasons.append(f"J值极低: {j:.2f}")
    elif j < -10:
        score += 25
        reasons.append(f"J值低位: {j:.2f}")
    elif j < 0:
        score += 15
        reasons.append(f"J值: {j:.2f}")

    # 缩量回调加分
    if today['vol'] < calculate_vol_ma(vols, 5) * 0.6:
        score += 20
        reasons.append("缩量回调")

    # BBI下方（低位）
    if today['close'] < bbi:
        score += 15
        reasons.append("BBI下方低位")

    # 价格在合理区间
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)
    if ma20 < today['close'] < ma60:
        score += 15
        reasons.append("中期均线区间")

    # 风险提示
    if j > 0:
        score -= 10
    if today['close'] > bbi * 1.05:
        score -= 15

    return max(0, min(100, score)), reasons


def score_trend(klines: List[Dict]) -> Tuple[float, str]:
    """
    评估趋势

    返回: (评分0-100, 趋势方向)
    """
    if len(klines) < 20:
        return 50, "震荡"

    closes = [k['close'] for k in klines]
    today = klines[-1]
    bbi = calculate_bbi(klines)

    ma5 = calculate_ma(closes, 5)
    ma20 = calculate_ma(closes, 20)
    ma60 = calculate_ma(closes, 60)

    # 趋势判断
    if ma5 > ma20 > ma60 and today['close'] > bbi:
        direction = "上升"
        score = 80 if today['pct_chg'] > 0 else 70
    elif ma5 < ma20 < ma60 and today['close'] < bbi:
        direction = "下降"
        score = 30
    else:
        direction = "震荡"
        score = 50

    # 短期动能
    if len(klines) >= 5:
        recent_pct = sum(k['pct_chg'] for k in klines[-5:])
        if recent_pct > 10:
            score += 10
        elif recent_pct < -10:
            score -= 10

    return max(0, min(100, score)), direction


def score_volume_pattern(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估量价形态
    """
    if len(klines) < 10:
        return 50, ["数据不足"]

    today = klines[-1]
    vols = [k['vol'] for k in klines]
    vol_ma5 = calculate_vol_ma(vols, 5)
    vol_ma10 = calculate_vol_ma(vols, 10)

    score = 50
    reasons = []

    # 量比
    vol_ratio = today['vol'] / vol_ma5
    if vol_ratio >= 2:
        score += 20
        reasons.append(f"倍量(量比{vol_ratio:.1f}x)")
    elif vol_ratio >= 1.5:
        score += 10
        reasons.append("放量")
    elif vol_ratio <= 0.5:
        score += 10
        reasons.append("缩量")
    else:
        score -= 5
        reasons.append("量能正常")

    # 涨跌配合
    if today['pct_chg'] > 3 and vol_ratio > 1.2:
        score += 15
        reasons.append("价涨量增(攻击形态)")
    elif today['pct_chg'] < -3 and vol_ratio > 1.2:
        score -= 15
        reasons.append("价跌量增(出货嫌疑)")

    return max(0, min(100, score)), reasons


def score_risk(klines: List[Dict]) -> Tuple[float, List[str]]:
    """
    评估风险
    """
    if len(klines) < 20:
        return 50, ["数据不足"]

    today = klines[-1]
    bbi = calculate_bbi(klines)
    closes = [k['close'] for k in klines]

    score = 100  # 初始100分，越高越安全
    warnings = []

    # 高位风险
    max_high = max(k['high'] for k in klines[-60:])
    drop_ratio = (max_high - today['close']) / max_high
    if drop_ratio < 0.1:
        score -= 30
        warnings.append("接近历史高位")
    elif drop_ratio < 0.2:
        score -= 15
        warnings.append("相对高位")

    # 跌破BBI风险
    if today['close'] < bbi:
        score -= 20
        warnings.append("跌破BBI")

    # 放量阴线风险
    for i in range(min(5, len(klines)-1)):
        k = klines[-(i+1)]
        prev = klines[-(i+2)] if i < len(klines)-2 else None
        if prev and k['close'] < prev['close'] and k['vol'] > prev['vol'] * 1.5:
            score -= 10
            warnings.append("近期有放量阴线")
            break

    # 连续下跌
    recent_3_drop = sum(1 for k in klines[-3:] if k['close'] < k['prev_close'])
    if recent_3_drop >= 3:
        score -= 15
        warnings.append("连续3天下跌")

    return max(0, min(100, score)), warnings


def analyze_screener_stock(
    ts_code: str,
    daily_klines: List[DailyData],
    *,
    name: str = "",
) -> StockScore:
    """综合评分单只股票（``daily_klines`` 为升序 ``DailyData``）。"""
    klines = _screener_bar_rows(ts_code, daily_klines)
    if not klines:
        return StockScore(ts_code=ts_code, name=name or ts_code)

    display_name = name or ts_code

    b1_score, b1_reasons = score_b1_opportunity(klines)
    trend_score, _trend_dir = score_trend(klines)
    volume_score, volume_reasons = score_volume_pattern(klines)
    risk_score, risk_warnings = score_risk(klines)

    # 总分采用固定权重，B1 机会权重最高，其次是趋势和量价，最后是风险安全垫。
    total_score = b1_score * 0.3 + trend_score * 0.25 + volume_score * 0.25 + risk_score * 0.2

    is_perfect, perfect_reasons = is_perfect_pattern(klines)
    if is_perfect:
        # “完美图形”只做加成，不改动四个子分本身，便于前端解释各因子来源。
        total_score = min(100, total_score * 1.1)
        b1_reasons.extend(perfect_reasons)

    return StockScore(
        ts_code=ts_code,
        name=display_name,
        score=round(total_score, 1),
        b1_score=round(b1_score, 1),
        trend_score=round(trend_score, 1),
        volume_score=round(volume_score, 1),
        risk_score=round(risk_score, 1),
        reasons=b1_reasons + volume_reasons,
        warnings=risk_warnings,
    )


def screen_stocks_from_universe(
    universe: List[tuple[str, str, List[DailyData]]],
    criteria: str = "b1",
) -> List[StockScore]:
    """全市场/批量选股。``universe`` 每项为 ``(ts_code, name, daily_klines)``。"""
    results: List[StockScore] = []
    for ts_code, stock_name, dkl in universe:
        if len(dkl) < 30:
            continue
        score = analyze_screener_stock(ts_code, dkl, name=stock_name)
        # 这里的 criteria 不是独立算法，只是对同一份评分结果做不同视角的过滤。
        if criteria == "b1" and score.b1_score >= 50:
            results.append(score)
        elif criteria == "perfect" and score.score >= 65:
            results.append(score)
        elif criteria == "oversold" and score.trend_score <= 40:
            results.append(score)
        elif criteria == "breakout" and score.volume_score >= 70:
            results.append(score)
    results.sort(key=lambda x: x.score, reverse=True)
    return results


def get_market_status_from_samples(latest_pct_chgs: List[float]) -> MarketStatus:
    """根据一组股票「最近一日」涨跌幅估算市场情绪（替代原 SQLite 扫盘）。"""
    today = datetime.now().strftime("%Y%m%d")
    if not latest_pct_chgs:
        return MarketStatus(
            trade_date=today,
            market_direction="NEUTRAL",
            market_strength=50.0,
            reasons=["无样本数据"],
        )

    rise_count = sum(1 for x in latest_pct_chgs if x > 0)
    total_count = len(latest_pct_chgs)
    rise_ratio = rise_count / total_count if total_count else 0.5

    # 这里只做轻量情绪估算，不引入指数、成交额等更复杂的市场宽度指标。
    if rise_ratio >= 0.6:
        direction = "LONG"
        strength = 75.0
        reasons = ["上涨家数占优", "市场活跃"]
    elif rise_ratio <= 0.4:
        direction = "SHORT"
        strength = 25.0
        reasons = ["下跌家数较多", "注意风险"]
    else:
        direction = "NEUTRAL"
        strength = 50.0
        reasons = ["多空均衡", "观望为主"]

    return MarketStatus(
        trade_date=today,
        is_trading=True,
        market_direction=direction,
        market_strength=strength,
        reasons=reasons,
    )


def format_stock_score(score: StockScore) -> str:
    """格式化股票评分"""
    return f"""
{score.ts_code} {score.name}
{'='*50}
综合评分: {score.score:.1f}/100 {score.rating}
{'='*50}
B1买点评分: {score.b1_score:.1f}
趋势评分: {score.trend_score:.1f}
量价评分: {score.volume_score:.1f}
风险评分: {score.risk_score:.1f}

利好因素:
{chr(10).join(f"  + {r}" for r in score.reasons) if score.reasons else "  无"}

风险提示:
{chr(10).join(f"  ! {w}" for w in score.warnings) if score.warnings else "  无"}
"""


def daily_workflow(
    *,
    market: MarketStatus,
    b1_stocks: List[StockScore],
    perfect_stocks: List[StockScore],
) -> Dict[str, Any]:
    """五步工作流的数据聚合（打印逻辑交给调用方）。"""
    return {
        "market": market,
        "b1_opportunities": b1_stocks[:5],
        "perfect_patterns": perfect_stocks[:5],
    }


def main() -> None:
    """原 SQLite CLI 已移除。"""
    raise SystemExit(
        "请使用 analyze_screener_stock / screen_stocks_from_universe / "
        "get_market_status_from_samples：K 线由 ``daily_data_list_from_polars``（本模块）提供。"
    )


if __name__ == "__main__":
    main()
