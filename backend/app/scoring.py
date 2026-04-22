from __future__ import annotations

from typing import Dict
import logging

import polars as pl

from app.config import (
    get_akshare_cache_ttl_seconds,
    get_akshare_history_days,
    get_akshare_max_workers,
    get_akshare_universe_size,
    get_data_path,
    get_data_source,
)
from app.schemas import ScoreRequest
from app.strategies import ScoringStrategy, get_strategy


FACTOR_COLUMNS = {
    "pe_weight": "pe_ratio",
    "momentum_weight": "momentum_20d",
    "volatility_weight": "volatility",
}

REQUIRED_COLUMNS = ["ticker", "name", "pe_ratio", "momentum_20d", "volatility"]

LOGGER = logging.getLogger(__name__)


def _raw_weights(payload: ScoreRequest) -> tuple[Dict[str, float], ScoringStrategy | None]:
    """按请求解析原始权重；若带 ``strategy_id`` 则用预设覆盖。"""
    if payload.strategy_id:
        strategy = get_strategy(payload.strategy_id)
        return strategy.weights(), strategy
    return {
        "pe_weight": payload.pe_weight,
        "momentum_weight": payload.momentum_weight,
        "volatility_weight": payload.volatility_weight,
    }, None


def normalize_weights(payload: ScoreRequest) -> Dict[str, float]:
    raw_weights, _ = _raw_weights(payload)
    total_abs = sum(abs(value) for value in raw_weights.values())
    return {
        key: (value / total_abs if total_abs else 0.0)
        for key, value in raw_weights.items()
    }


def _safe_zscore_expr(column_name: str) -> pl.Expr:
    mean_expr = pl.col(column_name).mean().over(pl.lit(1))
    std_expr = pl.col(column_name).std(ddof=0).over(pl.lit(1))
    return (
        pl.when(std_expr.fill_null(0) == 0)
        .then(0.0)
        .otherwise((pl.col(column_name) - mean_expr) / std_expr)
        .alias(f"{column_name}_zscore")
    )


def _scale_scores_to_100(frame: pl.DataFrame, score_column: str) -> pl.DataFrame:
    score_min = frame.select(pl.col(score_column).min()).item()
    score_max = frame.select(pl.col(score_column).max()).item()

    if score_min == score_max:
        return frame.with_columns(pl.lit(50.0).alias("total_score"))

    return frame.with_columns(
        (
            (pl.col(score_column) - score_min)
            / (score_max - score_min)
            * 100.0
        ).round(2).alias("total_score")
    )


def load_dataset() -> pl.DataFrame:
    data_source = get_data_source()

    if data_source == "parquet":
        return _load_dataset_from_parquet()

    if data_source == "akshare":
        return _load_dataset_from_akshare()

    # auto mode: prefer AKShare, fallback to local parquet when network/data source fails
    try:
        return _load_dataset_from_akshare()
    except Exception as ak_exc:
        LOGGER.warning(
            "AKShare dataset load failed in auto mode (%s). Fallback to parquet.",
            type(ak_exc).__name__,
        )
        return _load_dataset_from_parquet()


def _load_dataset_from_parquet() -> pl.DataFrame:
    data_path = get_data_path()
    if not data_path.exists():
        raise FileNotFoundError(
            f"Mock dataset not found at '{data_path}'. Run the generator script first."
        )
    dataset = pl.read_parquet(data_path)
    return _validate_dataset(dataset, source_name="parquet")


def _load_dataset_from_akshare() -> pl.DataFrame:
    from app.akshare_loader import load_akshare_dataset

    # universe_size=0 → 不做字典序截断，全市场进评分。
    # 历史上这里是用来限流网络请求的，现在数据源是 parquet，截断只会
    # 让靠后字典序（如 6xx/688 科创板）永远进不了排行榜。
    dataset = load_akshare_dataset(
        universe_size=0,
        history_days=get_akshare_history_days(),
        max_workers=get_akshare_max_workers(),
        cache_ttl_seconds=get_akshare_cache_ttl_seconds(),
    )
    return _validate_dataset(dataset, source_name="akshare")


def _validate_dataset(dataset: pl.DataFrame, source_name: str) -> pl.DataFrame:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in dataset.columns]
    if missing_columns:
        raise ValueError(
            f"{source_name} dataset missing required columns: {', '.join(missing_columns)}"
        )

    cleaned = dataset.select(REQUIRED_COLUMNS).drop_nulls(subset=REQUIRED_COLUMNS)
    if cleaned.height == 0:
        raise ValueError(f"{source_name} dataset has no valid rows after null filtering.")
    return cleaned


def _normalize_ticker_input(symbol: str) -> str:
    """宽容地把 'sh600000' / '600000' / ' 600000 ' 统一成 6 位代码。"""
    from app.market_data import _normalize_symbol

    return _normalize_symbol(symbol)


def _row_to_ranked(row: dict) -> dict:
    return {
        "rank": int(row["rank"]),
        "ticker": row["ticker"],
        "name": row["name"],
        "total_score": float(row["total_score"]),
        "factor_values": {
            "pe_ratio": float(row["pe_ratio"]),
            "momentum_20d": float(row["momentum_20d"]),
            "volatility": float(row["volatility"]),
        },
        "factor_zscores": {
            "pe_ratio": float(row["pe_ratio_zscore"]),
            "momentum_20d": float(row["momentum_20d_zscore"]),
            "volatility": float(row["volatility_zscore"]),
        },
    }


def _rank_dataset(dataset: pl.DataFrame, weights: Dict[str, float]) -> pl.DataFrame:
    """对一张宽表做 zscore → 加权和 → 归一化到 0~100 → 排名。"""
    scored = dataset.with_columns(
        [_safe_zscore_expr(column_name) for column_name in FACTOR_COLUMNS.values()]
    )
    raw_score_expr = sum(
        pl.col(f"{column_name}_zscore") * weights[weight_name]
        for weight_name, column_name in FACTOR_COLUMNS.items()
    )
    scored = scored.with_columns(raw_score_expr.alias("raw_score"))
    scored = _scale_scores_to_100(scored, "raw_score")
    scored = scored.sort("total_score", descending=True)
    scored = scored.with_row_index(name="rank", offset=1)
    return scored


def score_stocks(payload: ScoreRequest, top_n: int = 50) -> Dict[str, object]:
    raw_weights, applied_strategy = _raw_weights(payload)
    total_abs = sum(abs(v) for v in raw_weights.values())
    weights = {
        key: (value / total_abs if total_abs else 0.0)
        for key, value in raw_weights.items()
    }

    dataset = load_dataset()
    scored = _rank_dataset(dataset, weights)

    mode = "market"
    on_demand_ensured: dict | None = None
    target_symbol = (payload.symbol or "").strip()
    if target_symbol:
        mode = "single"
        normalized = _normalize_ticker_input(target_symbol)

        from app.market_data import _is_etf_symbol, ensure_symbol_cached

        if _is_etf_symbol(normalized):
            raise ValueError(
                f"Symbol '{normalized}' is an ETF, which is not supported by "
                "the current scoring pipeline (no PE ratio)."
            )

        matched = scored.filter(pl.col("ticker") == normalized)
        if matched.height == 0:
            LOGGER.info(
                "symbol %s miss in scoring dataset; trying on-demand cache fill",
                normalized,
            )
            try:
                on_demand_ensured = ensure_symbol_cached(normalized)
            except ValueError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise KeyError(
                    f"Symbol '{normalized}' is not cached and on-demand fetch "
                    f"failed: {exc}"
                ) from exc

            dataset = load_dataset()
            scored = _rank_dataset(dataset, weights)
            matched = scored.filter(pl.col("ticker") == normalized)
            if matched.height == 0:
                missing = []
                if (on_demand_ensured or {}).get("pe_ratio") is None:
                    missing.append("PE(东财估值分析暂无数据)")
                if (on_demand_ensured or {}).get("daily_rows", 0) < 21:
                    missing.append("历史日线不足 21 根")
                detail = "; ".join(missing) or "资料仍不完整"
                raise KeyError(
                    f"Symbol '{normalized}' fetched on demand but scoring still "
                    f"missing data ({detail})."
                )

        top_rows = matched.head(1)
    else:
        top_rows = scored.head(top_n)

    rows_out = [_row_to_ranked(row) for row in top_rows.iter_rows(named=True)]

    result: Dict[str, object] = {
        "normalized_weights": {
            key: round(value, 4) for key, value in weights.items()
        },
        "total_universe": dataset.height,
        "returned_count": len(rows_out),
        "mode": mode,
        "top_50": rows_out,
    }

    if on_demand_ensured is not None:
        result["on_demand_cached"] = {
            "symbol": on_demand_ensured["symbol"],
            "daily_rows": on_demand_ensured["daily_rows"],
            "pe_ratio": on_demand_ensured["pe_ratio"],
            "name": on_demand_ensured["name"],
        }

    if applied_strategy is not None:
        result["applied_strategy"] = {
            "id": applied_strategy.id,
            "name": applied_strategy.name,
            "description": applied_strategy.description,
            "weights": {
                key: round(value, 4)
                for key, value in applied_strategy.weights().items()
            },
        }

    return result
