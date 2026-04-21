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


FACTOR_COLUMNS = {
    "pe_weight": "pe_ratio",
    "momentum_weight": "momentum_20d",
    "volatility_weight": "volatility",
}

REQUIRED_COLUMNS = ["ticker", "name", "pe_ratio", "momentum_20d", "volatility"]

LOGGER = logging.getLogger(__name__)


def normalize_weights(payload: ScoreRequest) -> Dict[str, float]:
    raw_weights = {
        "pe_weight": payload.pe_weight,
        "momentum_weight": payload.momentum_weight,
        "volatility_weight": payload.volatility_weight,
    }
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

    dataset = load_akshare_dataset(
        universe_size=get_akshare_universe_size(),
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


def score_stocks(payload: ScoreRequest, top_n: int = 50) -> Dict[str, object]:
    weights = normalize_weights(payload)
    dataset = load_dataset()

    scored = dataset.with_columns(
        [_safe_zscore_expr(column_name) for column_name in FACTOR_COLUMNS.values()]
    )

    raw_score_expr = sum(
        pl.col(f"{column_name}_zscore") * weights[weight_name]
        for weight_name, column_name in FACTOR_COLUMNS.items()
    )

    scored = scored.with_columns(raw_score_expr.alias("raw_score"))
    scored = _scale_scores_to_100(scored, "raw_score")
    scored = scored.sort("total_score", descending=True).head(top_n)
    scored = scored.with_row_index(name="rank", offset=1)

    top_50 = []
    for row in scored.iter_rows(named=True):
        top_50.append(
            {
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
        )

    return {
        "normalized_weights": {
            key: round(value, 4) for key, value in weights.items()
        },
        "total_universe": dataset.height,
        "returned_count": len(top_50),
        "top_50": top_50,
    }
