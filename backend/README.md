# Backend

FastAPI + Polars backend for multi-factor stock scoring.

## Install

```powershell
python -m pip install -e .
```

## Run

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Or from repo root:

```powershell
.\scripts\start-backend.ps1
```

## Data Sources

The backend supports 3 data source modes:

- `DDTRADING_DATA_SOURCE=auto`: try AKShare first, fallback to local parquet.
- `DDTRADING_DATA_SOURCE=akshare`: use AKShare only (no fallback).
- `DDTRADING_DATA_SOURCE=parquet`: use local parquet only.

### AKShare options

```env
DDTRADING_AKSHARE_UNIVERSE_SIZE=300
DDTRADING_AKSHARE_HISTORY_DAYS=120
DDTRADING_AKSHARE_MAX_WORKERS=8
DDTRADING_AKSHARE_CACHE_TTL_SECONDS=600
```

### Parquet option

```env
DDTRADING_DATA_PATH=./data/mock_data.parquet
```

## Generate Mock Data

```powershell
python .\scripts\generate_mock_data.py
```

Output file:

- `backend/data/mock_data.parquet`

## API

- `GET /health`
- `POST /score`

`POST /score` request body:

```json
{
  "pe_weight": 0.3,
  "momentum_weight": 0.5,
  "volatility_weight": -0.2
}
```
