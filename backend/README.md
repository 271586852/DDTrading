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

## Data Source

The backend now uses Tushare as the only online data source.

### Required

```env
TUSHARE_TOKEN=your_tushare_token_here
```

### Tushare options

```env
DDTRADING_TUSHARE_UNIVERSE_SIZE=300
DDTRADING_TUSHARE_MAX_WORKERS=8
DDTRADING_TUSHARE_CACHE_TTL_SECONDS=600
DDTRADING_TUSHARE_DAILY_PARQUET_PATH=./data/tushare_daily.parquet
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
