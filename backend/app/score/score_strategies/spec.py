"""评分策略元数据：与具体因子算法解耦，由 ``score_engine`` 绑定实现。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ZScoreOrientation = Literal[
    "higher_better",
    "lower_better",
    "value_as_percentile_0_100",
    "none",
]

ValueFormatKind = Literal[
    "decimal_2",
    "percent_2",
    "decimal_1",
    "integer",
    "decimal_3",
]


@dataclass(frozen=True)
class FactorFieldMeta:
    """单条分项的展示与 z 分位语义（供 API / 前端强解耦渲染）。"""

    key: str
    label: str
    value_format: ValueFormatKind
    zscore_orientation: ZScoreOrientation = "higher_better"


@dataclass(frozen=True)
class ScoringStrategy:
    """单条评分策略。

    - ``score_engine``：已在 ``app.score.service`` 注册的算法管线标识。
    - ``factor_fields``：分项键及 UI 元数据，须与引擎返回的 ``factor_values`` 键一致。

    新增预设：放入本包内模块并导出 ``STRATEGY``，由 ``score_strategies`` 包扫描注册。
    新增算法：实现引擎后在 ``service`` 注册 ``score_engine`` 标识。
    """

    id: str
    name: str
    description: str
    score_engine: str
    factor_fields: tuple[FactorFieldMeta, ...]
    lookback_days: int = 120

    @property
    def factor_keys(self) -> tuple[str, ...]:
        return tuple(f.key for f in self.factor_fields)
