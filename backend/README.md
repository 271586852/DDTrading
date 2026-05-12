# Backend

FastAPI + DuckDB backend for multi-factor stock scoring and single-symbol backtesting.

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

Default config is loaded from `backend/.env` when using the script.

## Data Source

The backend uses Tushare as the online data source, DuckDB as the local market data cache, and a SimTradeLab-compatible backtest adapter.

### Required

```env
TUSHARE_TOKEN=your_tushare_token_here
```

### Tushare options

```env
DDTRADING_TUSHARE_MAX_REQUESTS_PER_MINUTE=420
DDTRADING_TUSHARE_MAX_WORKERS=4
DDTRADING_MARKET_DUCKDB_PATH=./data/market.duckdb
```

Create `backend/.env` directly and fill values from the sections above.

## Generate Mock Data

```powershell
python .\scripts\generate_mock_data.py
```

Output file:

- `backend/data/mock_data.parquet`

## API

- `GET /health`
- `POST /score`
- `GET /quote/{symbol}`
- `POST /refresh`
- `POST /backtest`

`POST /score` request body（`strategy_id` 必选，见 `GET /score-strategies`）:

```json
{
  "strategy_id": "zettaranc_composite",
  "symbol": "600000"
}
```

不传 `symbol` 时对本地 DuckDB 全市场按所选策略引擎评分并返回排行榜。
