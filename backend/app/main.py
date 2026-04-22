from __future__ import annotations

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.backtest import run_single_symbol_backtest
from app.config import get_cors_origins
from app.market_data import refresh_market_data
from app.quotes import fetch_quote
from app.schemas import (
    BacktestRequest,
    BacktestResponse,
    QuoteResponse,
    ScoreRequest,
    ScoreResponse,
    StrategyInfo,
)
from app.scoring import score_stocks
from app.strategies import list_strategies


app = FastAPI(
    title="DDTrading Scoring API",
    version="0.2.0",
    description=(
        "Backend API for multi-factor A-share ranking and single-symbol "
        "backtesting, backed by a local parquet cache built from AKShare."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/strategies", response_model=List[StrategyInfo])
def get_strategies() -> List[StrategyInfo]:
    """列出所有预设评分策略。"""
    return [
        StrategyInfo(
            id=s.id,
            name=s.name,
            description=s.description,
            weights=s.weights(),
        )
        for s in list_strategies()
    ]


@app.post("/score", response_model=ScoreResponse)
def calculate_scores(payload: ScoreRequest) -> ScoreResponse:
    try:
        result = score_stocks(payload)
    except KeyError as exc:
        # 单股模式下 symbol 不在缓存 → 404；否则（unknown strategy_id）→ 400
        status = 404 if payload.symbol else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    except ValueError as exc:
        # 单股模式下命中 ETF → 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(status_code=500, detail=f"Scoring failed: {exc}") from exc

    return ScoreResponse.model_validate(result)


@app.get("/quote/{symbol}", response_model=QuoteResponse)
def get_quote(symbol: str, bars: int = 120) -> QuoteResponse:
    """返回单只标的的最近 ``bars`` 根 K 线 + 最新收盘价 / 涨跌幅。

    数据来源：本地 parquet 缓存（``ashare_daily.parquet`` + ``stock_names.parquet``）。
    若代码不在缓存中，返回 404，提示先调用 ``/refresh``。
    """
    try:
        data = fetch_quote(symbol, bars=bars)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(status_code=500, detail=f"Quote lookup failed: {exc}") from exc

    return QuoteResponse.model_validate(data)


@app.post("/backtest", response_model=BacktestResponse)
def run_backtest_endpoint(payload: BacktestRequest) -> BacktestResponse:
    """单只股票回测（基于本地 parquet 缓存 + akquant）。"""
    try:
        return run_single_symbol_backtest(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}") from exc


@app.post("/refresh")
def refresh_data() -> dict[str, object]:
    """手动触发全市场日线 + 名称 + PE 快照的 parquet 重建。

    警告：首次或全量重建可能耗时 30~60 分钟，期间接口会长时间阻塞。
    建议在低峰期触发，或通过独立 worker 异步执行。
    """
    try:
        return {"status": "ok", "summary": refresh_market_data()}
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}") from exc
