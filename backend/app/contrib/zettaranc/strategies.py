"""战法识别（DuckDB / Polars 日线链路；无 SQLite）。

K 线请先转为 ``List[DailyData]``（见 :mod:`app.contrib.zettaranc.adapter`），
再调用 ``detect_all_strategies_from_klines`` 等入口。
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.contrib.zettaranc.adapter import bar_dict_rows_from_daily_data
from app.common.indicators import DailyData


class StrategyType(Enum):
    """战法类型"""
    # 基础战法
    B1 = "B1"                    # 买点1
    B2 = "B2"                    # 买点2（确认）
    B3 = "B3"                    # 买点3
    SB1 = "SB1"                  # 超级B1

    # 复合战法
    CHANGAN = "长安战法"          # 三日确认战法
    SI_FEN_ZHI_SAN = "四分之三阴量"  # 假突破识别
    NANA = "娜娜图形"            # 连续放量涨+缩量回调
    CHAOFAN = "超级B1"            # 超级买点

    # 异动战法
    YIDONG_DILIAN = "异动+地量地价"  # 异动后缩量买点

    # 特殊形态
    PINGHANG = "平行重炮"          # 双阳夹阴
    KENGQI = "坑里起好货"          # 填坑战法
    DUIchen = "对称VA"             # 对称战法


@dataclass
class StrategySignal:
    """战法信号"""
    ts_code: str
    trade_date: str
    strategy: StrategyType
    confidence: float              # 置信度 0-1
    description: str
    details: Dict[str, Any] = field(default_factory=dict)

    # 交易建议
    action: str = "WATCH"          # BUY/SELL/HOLD/WATCH
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    risk_ratio: Optional[float] = None


def _bar_rows(ts_code: str, klines: List[DailyData]) -> List[Dict[str, Any]]:
    rows = bar_dict_rows_from_daily_data(klines)
    for r in rows:
        r["ts_code"] = ts_code
    return rows


def calculate_ma(prices: List[float], period: int) -> float:
    """计算简单移动平均"""
    if len(prices) < period:
        return 0
    return sum(prices[-period:]) / period


def calculate_kdj(klines: List[Dict], period: int = 9) -> Tuple[float, float, float]:
    """计算 KDJ 指标"""
    if len(klines) < period:
        return 50, 50, 50

    rsv_list = []
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

    k = 50.0
    d = 50.0
    for rsv in rsv_list:
        k = (2/3) * k + (1/3) * rsv
        d = (2/3) * d + (1/3) * k

    j = 3 * k - 2 * d
    return round(k, 2), round(d, 2), round(j, 2)


def calculate_bbi(klines: List[Dict]) -> float:
    """计算 BBI"""
    if len(klines) < 24:
        return 0
    closes = [k['close'] for k in klines]
    ma3 = calculate_ma(closes, 3)
    ma6 = calculate_ma(closes, 6)
    ma12 = calculate_ma(closes, 12)
    ma24 = calculate_ma(closes, 24)
    return round((ma3 + ma6 + ma12 + ma24) / 4, 2)


def detect_b1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B1 买点

    B1 条件：
    1. J < -10（核心条件）
    2. 缩量回调（最佳）
    3. 价格在 BBI 下方或附近
    4. 非绿砖状态（连续下跌）
    """
    if index < 10:
        return None

    today = klines[index]
    k, d, j = calculate_kdj(klines[:index+1])

    # 核心条件：J < -10
    if j >= -10:
        return None

    # 最佳条件：缩量回调
    is_suoliang = today['is_suoliang']

    # 检查是否在连续下跌中（绿砖状态）
    # 绿砖：连续4根阴线
    recent_4 = klines[index-3:index+1]
    yin_count = sum(1 for k in recent_4 if k['is_yinxian'])

    # B1 买点
    bbi = calculate_bbi(klines[:index+1])
    price = today['close']

    # 计算止损位
    stop_loss = today['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B1,
        confidence=0.8 if is_suoliang else 0.6,
        description=f"B1买点 J={j:.2f}" + (" 缩量回调" if is_suoliang else ""),
        details={
            'j': j,
            'k': k,
            'd': d,
            'is_suoliang': is_suoliang,
            'yin_count_4': yin_count,
            'bbi': bbi,
            'price': price,
        },
        action="BUY",
        stop_loss=stop_loss,
    )


def detect_b2(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B2 买点

    B2 条件（B1后的确认信号）：
    1. 前几日有B1（J<-10）
    2. 放量长阳（涨幅>=4%）
    3. J值拐头（>-10）
    4. 无上影线最好
    """
    if index < 15:
        return None

    today = klines[index]

    # 检查是否有B1在前几日
    has_b1 = False
    prev_j_list = []
    for i in range(5, min(15, index)):
        pk, pd, pj = calculate_kdj(klines[:index-i+1])
        prev_j_list.append(pj)
        if pj < -10:
            has_b1 = True
            break

    if not has_b1:
        return None

    # 放量长阳
    is_beidou = today['is_beidou']
    pct_chg = today['pct_chg']
    is_long_yang = pct_chg >= 4

    # 无上影线
    has_upper_shadow = today['high'] > today['close'] * 1.01

    if not (is_long_yang and is_beidou):
        return None

    # 计算J值
    k, d, j = calculate_kdj(klines[:index+1])

    # B2 确认
    stop_loss = today['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B2,
        confidence=0.85 if not has_upper_shadow else 0.75,
        description=f"B2确认 涨{pct_chg:.2f}% J={j:.2f}",
        details={
            'j': j,
            'pct_chg': pct_chg,
            'is_beidou': is_beidou,
            'has_upper_shadow': has_upper_shadow,
            'price': today['close'],
        },
        action="BUY",
        stop_loss=stop_loss,
    )


def detect_b3(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测 B3 中继买点

    B3 条件：
    1. B2后出现
    2. 分歧转一致（小阳线）
    3. 涨幅<2%
    4. 振幅<7%
    """
    if index < 20:
        return None

    today = klines[index]
    prev_2 = klines[index-2] if index >= 2 else None
    prev_3 = klines[index-3] if index >= 3 else None

    # 检查前几日是否有B2
    has_b2 = False
    for i in range(3, min(10, index)):
        if klines[index-i]['pct_chg'] >= 4 and klines[index-i]['is_beidou']:
            has_b2 = True
            break

    if not has_b2:
        return None

    # B3：小阳线，分歧转一致
    pct_chg = today['pct_chg']
    amplitude = (today['high'] - today['low']) / today['prev_close'] * 100

    if not (0 < pct_chg < 2 and amplitude < 7):
        return None

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.B3,
        confidence=0.7,
        description=f"B3中继 涨{pct_chg:.2f}% 振幅{amplitude:.2f}%",
        details={
            'pct_chg': pct_chg,
            'amplitude': amplitude,
            'price': today['close'],
        },
        action="BUY",
        stop_loss=today['low'],
    )


def detect_sb1(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测超级B1

    超级B1条件：
    1. 缩量回调到极致
    2. 突然放量下跌（震仓）
    3. 继续缩量企稳
    4. J出现负值
    """
    if index < 10:
        return None

    today = klines[index]
    prev_1 = klines[index-1] if index >= 1 else None
    prev_2 = klines[index-2] if index >= 2 else None

    if not (prev_1 and prev_2):
        return None

    # 检查前2天是否有放量下跌
    is_drop_vol = prev_2['close'] < prev_2['open'] and prev_2['vol'] > klines[index-3]['vol'] * 1.5

    if not is_drop_vol:
        return None

    # 今日缩量企稳
    is_suoliang = today['is_suoliang']

    # J值
    k, d, j = calculate_kdj(klines[:index+1])

    if j >= -5:
        return None

    # 超级B1确认
    stop_loss = prev_2['low']

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.SB1,
        confidence=0.9,
        description=f"超级B1 J={j:.2f} 放量跌后缩量企稳",
        details={
            'j': j,
            'drop_vol': prev_2['vol'],
            'is_suoliang': is_suoliang,
            'price': today['close'],
        },
        action="BUY",
        stop_loss=stop_loss,
    )


def detect_changan(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测长安战法（胜率75%）

    三条件：
    1. 第一天为B1（J<-13）
    2. 第二天为放量长阳，J值拐头
    3. 第三天为分歧转一致且缩半量
    """
    if index < 3:
        return None

    day1 = klines[index-2]
    day2 = klines[index-1]
    day3 = klines[index]

    # 第一天：B1（J<-13）
    k1, d1, j1 = calculate_kdj(klines[:index-1])
    if j1 >= -13:
        return None

    # 第二天：放量长阳，J拐头
    k2, d2, j2 = calculate_kdj(klines[:index])
    if not (day2['pct_chg'] >= 4 and day2['is_beidou'] and j2 > j1):
        return None

    # 第三天：分歧转一致，缩半量
    pct_chg = day3['pct_chg']
    amplitude = (day3['high'] - day3['low']) / day3['prev_close'] * 100
    is_half_vol = day3['vol'] <= day2['vol'] * 0.5

    if not (0 < pct_chg < 2 and amplitude < 7 and is_half_vol):
        return None

    return StrategySignal(
        ts_code=day3['ts_code'],
        trade_date=day3['trade_date'],
        strategy=StrategyType.CHANGAN,
        confidence=0.75,
        description=f"长安战法确认 胜率75%",
        details={
            'j1': j1,
            'j2': j2,
            'day2_pct': day2['pct_chg'],
            'day3_pct': pct_chg,
            'amplitude': amplitude,
        },
        action="BUY",
        stop_loss=day3['low'],
    )


def detect_sifen_zhiyi_sanyin(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测四分之三阴量战法

    条件：大阳线后次日阴量 > 阳量 × 0.75 = 假突破
    """
    if index < 1:
        return None

    today = klines[index]
    yesterday = klines[index-1]

    # 昨日大阳线
    if yesterday['pct_chg'] < 3:
        return None

    # 今日阴线
    if today['close'] >= today['open']:
        return None

    # 阴量判断
    vol_ratio = today['vol'] / yesterday['vol']

    if vol_ratio > 0.75:
        # 假突破！主力出货
        return StrategySignal(
            ts_code=today['ts_code'],
            trade_date=today['trade_date'],
            strategy=StrategyType.SI_FEN_ZHI_SAN,
            confidence=0.9,
            description=f"假突破！阴量{vol_ratio:.0%}超过阳量75%",
            details={
                'yang_vol': yesterday['vol'],
                'yin_vol': today['vol'],
                'vol_ratio': vol_ratio,
            },
            action="SELL",
        )

    return None


def detect_nana(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测娜娜图形

    四条件同时满足：
    1. 连续放量上涨
    2. 顶部无巨量阴线
    3. 连续缩量回调
    4. J下到负值
    """
    if index < 10:
        return None

    # 检查连续放量上涨（最近3-5天）
    rise_count = 0
    for i in range(index-4, index+1):
        if i < 1:
            continue
        if klines[i]['is_rise'] and klines[i]['is_beidou']:
            rise_count += 1

    if rise_count < 3:
        return None

    # 检查顶部无巨量阴线
    for i in range(index-4, index):
        if klines[i]['is_fangliang_yinxian']:
            return None

    # 检查连续缩量回调
    suoliang_count = 0
    for i in range(index-4, index):
        if klines[i]['is_suoliang']:
            suoliang_count += 1

    if suoliang_count < 2:
        return None

    # J值负值
    k, d, j = calculate_kdj(klines[:index+1])
    if j >= 0:
        return None

    return StrategySignal(
        ts_code=klines[index]['ts_code'],
        trade_date=klines[index]['trade_date'],
        strategy=StrategyType.NANA,
        confidence=0.85,
        description=f"娜娜图形 J={j:.2f} 连续放量涨+缩量回调",
        details={
            'j': j,
            'rise_count': rise_count,
            'suoliang_count': suoliang_count,
        },
        action="BUY",
        stop_loss=klines[index]['low'],
    )


def detect_yidong_dilian(klines: List[Dict], index: int) -> Optional[StrategySignal]:
    """
    检测异动+地量地价战法

    三步：
    1. 异动 = 突然放量，资金进场
    2. 异动后缩量回调
    3. 地量 = 最佳B1买点
    """
    if index < 5:
        return None

    today = klines[index]

    # 检查前几天是否有异动
    yidong_index = None
    for i in range(index-1, max(0, index-10), -1):
        # 异动：放量+上涨
        if klines[i]['is_beidou'] and klines[i]['is_rise']:
            yidong_index = i
            break

    if yidong_index is None:
        return None

    # 检查异动后是否缩量回调
    days_after = index - yidong_index
    if days_after < 2:
        return None

    # 回调期间应该有缩量
    has_suoliang = any(klines[j]['is_suoliang'] for j in range(yidong_index+1, index+1))

    # 今日地量（最佳买点）
    if not today['is_suoliang']:
        return None

    # J值判断
    k, d, j = calculate_kdj(klines[:index+1])

    return StrategySignal(
        ts_code=today['ts_code'],
        trade_date=today['trade_date'],
        strategy=StrategyType.YIDONG_DILIAN,
        confidence=0.8,
        description=f"异动+地量地价 异动后{days_after}天缩量回调 J={j:.2f}",
        details={
            'yidong_date': klines[yidong_index]['trade_date'],
            'days_after': days_after,
            'j': j,
        },
        action="BUY",
        stop_loss=today['low'],
    )


def detect_all_strategies_from_klines(
    ts_code: str,
    daily_klines: List[DailyData],
) -> List[StrategySignal]:
    """检测所有战法信号（``daily_klines`` 为按日期升序的 ``DailyData``）。"""
    klines = _bar_rows(ts_code, daily_klines)
    if not klines:
        return []

    signals: List[StrategySignal] = []

    for i in range(10, len(klines)):
        signal = detect_b1(klines, i)
        if signal:
            signals.append(signal)

        signal = detect_b2(klines, i)
        if signal:
            signals.append(signal)

        signal = detect_b3(klines, i)
        if signal:
            signals.append(signal)

        signal = detect_sb1(klines, i)
        if signal:
            signals.append(signal)

        signal = detect_changan(klines, i)
        if signal:
            signals.append(signal)

        signal = detect_sifen_zhiyi_sanyin(klines, i)
        if signal:
            signals.append(signal)

        signal = detect_nana(klines, i)
        if signal:
            signals.append(signal)

        signal = detect_yidong_dilian(klines, i)
        if signal:
            signals.append(signal)

    signals.sort(key=lambda x: x.trade_date, reverse=True)
    return signals


def get_latest_signal_from_klines(
    ts_code: str,
    daily_klines: List[DailyData],
) -> Optional[StrategySignal]:
    """取最新一条战法信号。"""
    signals = detect_all_strategies_from_klines(ts_code, daily_klines)
    return signals[0] if signals else None


def format_signal(signal: StrategySignal) -> str:
    """格式化输出信号"""
    action_emoji = {
        'BUY': '[买入]',
        'SELL': '[卖出]',
        'HOLD': '[持有]',
        'WATCH': '[观望]',
    }

    return f"""
{'='*60}
{signal.strategy.value} 信号
{'='*60}
股票: {signal.ts_code}
日期: {signal.trade_date}
置信度: {signal.confidence*100:.0f}%
描述: {signal.description}

交易建议: {action_emoji.get(signal.action, signal.action)}
{f'目标价: {signal.target_price:.2f}' if signal.target_price else ''}
{f'止损价: {signal.stop_loss:.2f}' if signal.stop_loss else ''}

详细: {signal.details}
{'='*60}
"""


def analyze_with_strategies_from_klines(
    ts_code: str,
    daily_klines: List[DailyData],
) -> Dict[str, Any]:
    """综合战法分析，返回统计与最近信号列表。"""
    signals = detect_all_strategies_from_klines(ts_code, daily_klines)

    strategy_stats: Dict[str, Any] = {}
    for s in signals:
        name = s.strategy.value
        if name not in strategy_stats:
            strategy_stats[name] = {
                "count": 0,
                "signals": [],
            }
        strategy_stats[name]["count"] += 1
        strategy_stats[name]["signals"].append(s)

    latest = signals[0] if signals else None

    return {
        "ts_code": ts_code,
        "total_signals": len(signals),
        "strategy_stats": strategy_stats,
        "latest_signal": latest,
        "all_signals": signals[:20],
    }


def main() -> None:
    """原 SQLite CLI 已移除。"""
    raise SystemExit(
        "请使用 ``app.contrib.zettaranc.adapter`` 与 detect_all_strategies_from_klines(ts_code, daily_klines)。"
    )


if __name__ == "__main__":
    main()
