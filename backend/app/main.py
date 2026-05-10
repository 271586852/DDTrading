from __future__ import annotations

from typing import List, Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

from app.backtest import export_single_symbol_backtest_report, run_single_symbol_backtest
from app.config import get_cors_origins
from app.market_data import get_market_data_cache_revision, refresh_market_data
from app.quotes import fetch_quote
from app.schemas import (
    BacktestRequest,
    BacktestReportRequest,
    BacktestResponse,
    MarketScoreJobStarted,
    MarketScoreJobStatus,
    QuoteResponse,
    ScoreRequest,
    ScoreResponse,
    StrategyInfo,
    TradeStrategyInfo,
)
from app.score_market_job import complete_job, create_job, fail_job, get_job, update_job
from app.scoring import score_stocks
from app.strategies import list_strategies
from app.trade_strategies import list_trade_strategies


app = FastAPI(
    title="DDTrading Scoring API",
    version="0.2.0",
    description=(
        "Backend API for multi-factor A-share ranking and single-symbol "
        "backtesting, backed by a local parquet cache built from Tushare."
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


@app.get("/market-data-revision")
def market_data_revision() -> dict[str, float]:
    """返回当前本地全市场数据版本号，用于前端判断全市场评分缓存是否过期。"""
    return {"market_data_revision": get_market_data_cache_revision()}


@app.get("/score-strategies", response_model=List[StrategyInfo])
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


def _run_market_score_job(job_id: str, payload: ScoreRequest) -> None:
    """后台执行全市场评分并更新任务状态。"""
    update_job(job_id, status="running", progress=0, stage="开始…")

    def report(pct: int, msg: str) -> None:
        update_job(job_id, status="running", progress=pct, stage=msg)

    try:
        result = score_stocks(payload, progress=report)
        complete_job(job_id, result)
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id, str(exc))


@app.post("/score/market-job", response_model=MarketScoreJobStarted)
def start_market_score_job(
    payload: ScoreRequest,
    background_tasks: BackgroundTasks,
) -> MarketScoreJobStarted:
    """启动异步全市场评分（不传 symbol），供前端轮询进度。"""
    if (payload.symbol or "").strip():
        raise HTTPException(
            status_code=400,
            detail="全市场异步任务请勿传 symbol，请改用 POST /score 做单股同步评分。",
        )
    job_id = create_job()
    background_tasks.add_task(_run_market_score_job, job_id, payload)
    return MarketScoreJobStarted(job_id=job_id)


@app.get("/score/market-job/{job_id}", response_model=MarketScoreJobStatus)
def get_market_score_job(job_id: str) -> MarketScoreJobStatus:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期。")
    result_model = (
        ScoreResponse.model_validate(job.result) if job.result is not None else None
    )
    return MarketScoreJobStatus(
        status=job.status,  # type: ignore[arg-type]
        progress=job.progress,
        stage=job.stage,
        result=result_model,
        error=job.error,
    )


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


@app.get("/trade-strategies", response_model=List[TradeStrategyInfo])
def get_trade_strategies() -> List[TradeStrategyInfo]:
    """列出所有可用于 ``/backtest`` 的交易策略。"""
    return [
        TradeStrategyInfo(id=spec.id, name=spec.name, description=spec.description)
        for spec in list_trade_strategies()
    ]


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


@app.post("/backtest/report")
def export_backtest_report_endpoint(payload: BacktestReportRequest) -> Response:
    """导出单只股票回测 HTML 报告。"""
    try:
        html = export_single_symbol_backtest_report(payload)
        filename = f"backtest_{payload.symbol.zfill(6)}_{payload.start_date}_{payload.end_date}.html"
        return Response(
            content=html,
            media_type="text/html; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(
            status_code=500, detail=f"Backtest report export failed: {exc}"
        ) from exc


@app.post("/refresh")
def refresh_data(
    mode: Literal["full", "incremental"] = "incremental",
    force: bool = False,
) -> dict[str, object]:
    """手动刷新全市场日线 + 名称 + PE 快照。

    - ``mode=incremental``: 默认增量刷新，日线按已缓存最后日期补拉，PE 按日补齐。
    - ``mode=full``: 全量重建三张 parquet；首次或全量重建可能耗时 30~60 分钟。
    - ``force=true``: 跳过「距上次成功刷新不足冷却窗口」的短路（默认冷却见环境变量）。
    """
    try:
        summary = refresh_market_data(mode=mode, force=force)
        if summary.get("skipped"):
            return {"status": "skipped", "mode": mode, "summary": summary}
        return {"status": "ok", "mode": mode, "summary": summary}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}") from exc
