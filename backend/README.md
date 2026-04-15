# Backend

`FastAPI + Polars` 后端服务，负责读取本地 Parquet 数据、执行横截面标准化，并返回 Top 50 股票评分结果。

## 安装

```powershell
python -m pip install -e .
```

## 生成 Mock 数据

```powershell
python .\scripts\generate_mock_data.py
```

输出文件默认位于：

- `backend/data/mock_data.parquet`

字段包括：

- `ticker`
- `name`
- `pe_ratio`
- `momentum_20d`
- `volatility`

## 启动服务

推荐命令：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

Windows 当前环境下不建议使用 `--reload`。

也可以从仓库根目录执行：

```powershell
.\scripts\start-backend.ps1
```

## 环境变量

后端支持以下环境变量：

```env
DDTRADING_DATA_PATH=./data/mock_data.parquet
DDTRADING_CORS_ORIGINS=http://127.0.0.1:3000
```

说明：

- `DDTRADING_DATA_PATH`：切换数据文件位置
- `DDTRADING_CORS_ORIGINS`：逗号分隔多个允许访问的前端来源

示例文件见 `backend/.env.example`。

## API

### `GET /health`

用于健康检查。

### `POST /score`

请求示例：

```json
{
  "pe_weight": 0.3,
  "momentum_weight": 0.5,
  "volatility_weight": -0.2
}
```

返回包含：

- `normalized_weights`
- `total_universe`
- `returned_count`
- `top_50`

## 权重逻辑

接口支持正负权重，内部会按绝对值总和归一化，确保即使前端没有严格传入 `1.0` 总和，也能保持相对强弱和方向不变。
