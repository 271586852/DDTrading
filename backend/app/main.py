from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_cors_origins
from app.schemas import ScoreRequest, ScoreResponse
from app.scoring import score_stocks


app = FastAPI(
    title="DDTrading Scoring API",
    version="0.1.0",
    description="MVP API for multi-factor stock ranking (AKShare or Parquet data source).",
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


@app.post("/score", response_model=ScoreResponse)
def calculate_scores(payload: ScoreRequest) -> ScoreResponse:
    try:
        result = score_stocks(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive API boundary
        raise HTTPException(status_code=500, detail=f"Scoring failed: {exc}") from exc

    return ScoreResponse.model_validate(result)
