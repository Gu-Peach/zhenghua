# Web 前端

线表智能提取系统的新前端，使用 React + Vite + TypeScript。本阶段通过类型化 Mock API 构建交互式工作台，不依赖旧 `frontend/`，也不修改当前 Python 后端。

## 目录结构

```text
apps/web/
├─ public/                 # 原样发布的静态文件
├─ src/
│  ├─ apis/                # HTTP Client、接口函数、DTO 和 Mock 适配器
│  ├─ assets/              # 全局样式和打包资源
│  ├─ components/          # 可复用业务组件
│  ├─ directives/          # 预留的底层 DOM 行为适配器
│  ├─ hooks/               # 可复用交互逻辑
│  ├─ layout/              # 路由布局
│  ├─ router/              # React Router 路由和后续守卫
│  ├─ stores/              # 跨页面状态
│  ├─ views/               # 路由页面
│  ├─ App.tsx
│  └─ main.tsx
├─ .env.example
├─ index.html
├─ package.json
├─ tsconfig.json
└─ vite.config.ts
```

## 路由

```text
/login
/projects
/projects/:projectId
```

项目页包含 Header、顶部资源导航（线表工作区 / 图纸库 / 规则库）、`项目 -> 工作区 -> 图纸` 树、结构化线表、图纸证据，以及 Supervisor 主 Agent 运行监工区。

默认 Mock 模式下仍需显式开启工作台内的“模拟链路”开关才运行流程。首次加载不展示预置历史 Agent 事件；上传后先登记源 PDF，Stage 1 完成后才呈现工作区和拆分页。右侧以淡化流式文本展示主 Agent 思考，并依序呈现加粗的子 Agent、等待标记和完成勾选。自然语言修复可模拟用户直接给答案、同页/跨页重提取、问题归因和待审核规则候选展示。Mock 不会处理 PDF 内容、写入数据库或发布生产规则。

## API 模式

需要本地覆盖配置时，将 `.env.example` 复制为 `.env.local`：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_USE_MOCKS=true
```

`VITE_USE_MOCKS=true` 时，`src/apis` 使用类型化本地数据；新 `apps/api` 契约可用后改为 `false`。

真实模式目前的前端适配器预期使用图纸库、规则库和 Supervisor run/events API；对应后端端点与权限契约尚未完成，联调前不要关闭 Mock。

## 启动

在仓库根目录执行：

```powershell
corepack pnpm install
corepack pnpm dev:web
```

访问 `http://127.0.0.1:5174`。

质量检查：

```powershell
corepack pnpm typecheck:web
corepack pnpm lint:web
corepack pnpm build:web
```

旧 Vite 前端继续使用 `5173`，新前端使用 `5174`，迁移期间可以同时运行。
