# DDTrading

基于 `Next.js + FastAPI + Polars` 的量化选股评分系统 MVP。

当前已完成：

- `backend/`：Parquet Mock 数据生成、因子标准化、评分接口
- `frontend/`：Dark Cyber-SaaS 风格控制台、Zustand 状态管理、TanStack Table 排行榜、ECharts 微图表
- `scripts/`：前后端启动脚本与一键联调脚本

## 项目结构

```text
DDTrading/
├─ backend/
├─ frontend/
└─ scripts/
```

## 环境要求

- Python `3.11+`
- Node.js `22+`
- `corepack` 可用，用于执行 `pnpm`

## 首次安装

### 1. 安装后端依赖

```powershell
cd .\backend
python -m pip install -e .
python .\scripts\generate_mock_data.py
```

### 2. 安装前端依赖

```powershell
cd ..\frontend
corepack pnpm install
```

## 本地启动

### 方式一：分别启动

后端：

```powershell
cd .\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

前端：

```powershell
cd .\frontend
corepack pnpm dev
```

默认访问地址：

- 前端：`http://127.0.0.1:3000`
- 后端：`http://127.0.0.1:8011`
- 接口文档：`http://127.0.0.1:8011/docs`

### 方式二：使用启动脚本

只启动后端：

```powershell
.\scripts\start-backend.ps1
```

只启动前端：

```powershell
.\scripts\start-frontend.ps1
```

一键拉起前后端：

```powershell
.\scripts\start-dev.ps1
```

脚本会默认使用：

- 前端端口 `3000`
- 后端端口 `8011`
- 前端 API 地址 `http://127.0.0.1:8011`

## 环境变量

### 前端

在 `frontend/.env.local` 中配置：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8011
```

示例文件见 `frontend/.env.example`。

### 后端

在 `backend/.env` 中配置：

```env
TUSHARE_TOKEN=your_tushare_token_here
DDTRADING_CORS_ORIGINS=http://127.0.0.1:3010,http://localhost:3010
```

说明：

- `TUSHARE_TOKEN` 为后端抓取真实行情所需令牌
- `DDTRADING_CORS_ORIGINS` 支持逗号分隔多个前端来源

## 前后端联调约定

- 默认后端端口使用 `8011`
- 默认前端端口使用 `3000`
- 前端通过 `NEXT_PUBLIC_API_BASE_URL` 调用后端 `/score`
- 后端通过 `DDTRADING_CORS_ORIGINS` 控制允许访问的前端地址

## 部署准备建议

### 前端部署

- 推荐部署到 Vercel
- 必配环境变量：`NEXT_PUBLIC_API_BASE_URL`
- 生产环境应将其指向真实 API 域名，例如 `https://api.example.com`

### 后端部署

- 可部署到云主机、Docker 容器或 PaaS
- 启动命令示例：

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8011
```

- 生产环境建议把 `DDTRADING_CORS_ORIGINS` 设置为真实前端域名
- 行情与评分数据来自 Tushare，本地缓存在 DuckDB：配置 `TUSHARE_TOKEN`，按需设置 `DDTRADING_MARKET_DUCKDB_PATH`、`DDTRADING_DAILY_HISTORY_DAYS` 等（见 `backend/.env.example`）

## 常见问题

### Windows 下 `--reload` 报 `WinError 10013`

当前环境下建议不要使用：

```powershell
uvicorn app.main:app --reload
```

请改用固定端口、无热重载启动，例如：

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8011
```

### 前端显示 `Failed to fetch`

优先检查：

- 后端是否正在 `8011` 端口运行
- `frontend/.env.local` 中的 `NEXT_PUBLIC_API_BASE_URL` 是否正确
- 修改环境变量后是否重启了前端开发服务器
