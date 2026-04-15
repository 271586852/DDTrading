# Frontend

基于 `Next.js App Router + Tailwind CSS + Zustand + TanStack Table + ECharts` 的量化评分前端。

## 安装依赖

```powershell
corepack pnpm install
```

## 环境变量

在 `frontend/.env.local` 中配置后端地址：

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8011
```

示例文件见 `frontend/.env.example`。

## 本地启动

```powershell
corepack pnpm dev
```

默认访问：

- `http://127.0.0.1:3000`

也可以从仓库根目录使用脚本：

```powershell
.\scripts\start-frontend.ps1
```

## 可用命令

```powershell
corepack pnpm dev
corepack pnpm lint
corepack pnpm build
```

## 部署准备

推荐部署到 Vercel、Netlify 或任意支持 Next.js 的 Node 平台。

部署前请确认：

- 已设置 `NEXT_PUBLIC_API_BASE_URL`
- 该地址指向真实可访问的后端 API
- 后端 CORS 已允许前端部署域名

## 当前界面能力

- 左侧：赛博风策略控制台，支持权重预设、实时预览、debounce 自动请求
- 右侧：TanStack Table 排行榜，支持评分进度条、悬浮动效和 ECharts 微图表
