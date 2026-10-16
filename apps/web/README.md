# Web 前端

登录后直接进入工作区：有项目默认打开首个项目，无项目显示完整空工作区并可上传/登记规则。重命名和删除在左侧项目树，独立项目目录页已取消。见[入口记录](../../docs/apps/web/changelog/2026-10-16-workspace-entry.md)。

2026-10-16当前为三表数据管理界面：选择规则后保存PDF、项目/JSON图纸目录、批次线表/行级CRUD与规则引用预览。上传不会启动Agent，AI输入明确未接入。刷新前需重启8000后端加载新接口；详见[交付](../../docs/apps/web/changelog/2026-10-16-simple-management.md)。下文旧聊天/规则发布说明仅为历史记录。

2026-10-13 聊天微调：主面板改为“电气图纸与线表智能助手”，日常回复通过 SSE 累积到同一条对话，不显示确认卡片或刷新线表；任务说明逐字显示完后才呈现后续任务/确认卡片。上传提示使用 Stage 1/2 提取路线，流中断保留已收到文字并停止光标。详见[记录](../../docs/apps/web/changelog/2026-10-13-supervisor-chat.md)。

线表智能提取系统的新前端，使用 React + Vite + TypeScript。当前默认读取真实 Server 数据，不依赖旧 `frontend/`。旧 Mock 资产保留但不参与运行。

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

上传 PDF 后自动创建真实项目并向 Agent 请求识别；类型确认后运行三阶段，Stage 1 发布后从 Server 刷新图纸树。右侧显示真实公开计划/诊断依据和阶段卡片；数据修订与规则候选均保留人工确认。新任务可重置短期会话，浏览器刷新可重新订阅原 run；Agent 重启后的短期会话不可恢复。

每阶段卡片原位更新，最终类型确认提示可见；进度断线按序号自动续传，也可点击“重新连接进度”，不会重新提交任务。图纸链接过期可刷新；编辑电压/端子排会影响同线号的所有记录，失败重试复用同一提交键。

规则库可点击“新建规则包”，选择已发布模板，填写唯一规则标识/名称/识别说明与特征，可展开编辑三阶段 Prompt，勾选确认后创建并注册。图片 Few-shot、expected JSON、Schema 和算法继承模板；当前只支持已实现的 ZH adapter。创建者有删除按钮，确认后停用并刷新列表，历史项目保留原包。已有 key 的规则改动继续走候选评测/审核/发布。

本次规则包功能的应用 strict 类型检查和 7 项浏览器夹具通过；本机 node_modules 文件读取 EPERM 阻塞 lint、production build 和 OpenAPI 自动生成。API 快照已导出，客户端新契约暂手动同步；权限修复后需重新生成并执行完整检查，见[实施记录](../../docs/service/server/changelog/2026-10-12-rule-package-lifecycle.md)。

## API 模式

需要本地覆盖配置时，将 `.env.example` 复制为 `.env.local`：

```env
VITE_API_BASE_URL=
```

开发环境默认同源 `/api`，Vite 转发到 8000，避免 localhost/127.0.0.1 混用导致 refresh cookie 丢失。生产部署同源反向代理 `/api` 到 Server。前端不得配置内部 Agent Token 或 Supabase service-role。

先启动 [Server](../../services/server/README.md) 和 Agent，再启动 Web。使用已有 Supabase 用户的邮箱/密码登录；用户 UUID 不能代替登录。无需把模型或数据库密钥放入浏览器。

线表工具栏“新增端子”将端子加入已有线号，指定来源页及可选跨页目标；行内删除需确认。操作保留其他 ID/线号并刷新结果。增删需要 Server PostgreSQL 事务连接；本地使用 Server README 中的 `run_local_api.py`，无连接返回 503，不绕过审计。

## 启动

以下命令使用 Windows PowerShell。首次安装需要 Node.js 和 Corepack；所有命令从仓库根目录执行，克隆路径不同时调整 `Set-Location`。完整本地联调按 Agent → Server → Web 的顺序启动，每个服务使用独立终端。

首次安装依赖（已有依赖时跳过）：

```powershell
Set-Location E:\project\zhenghua_test
corepack pnpm install
if (-not (Test-Path apps\web\.env.local)) { Copy-Item apps\web\.env.example apps\web\.env.local }
```

启动前端开发服务：

```powershell
Set-Location E:\project\zhenghua_test
corepack pnpm dev:web
```

访问 `http://127.0.0.1:5174`，登录页为 `/login`。`VITE_API_BASE_URL` 默认留空，`/api` 由 Vite 代理到 `http://127.0.0.1:8000`；后端启动见 [Server README](../../services/server/README.md)，AI 服务启动见 [Agent README](../../services/agent/README.md#启动)。端口被占用时 Vite 会报错，不会自动切换端口；开发服务可在所属终端按 `Ctrl+C` 停止。

质量检查：

```powershell
corepack pnpm typecheck:web
corepack pnpm lint:web
corepack pnpm build:web
```

浏览器回归：`corepack pnpm --filter @wiring/web exec playwright test`。使用显式HTTP夹具、本地Chrome和独立5186端口，截图存于忽略的`.runtime/simple-management-browser`，不调用模型。旧业务表/Agent合约留在tests/legacy-workbench.fixture.ts，不计入当前回归。生成接口类型：先执行`apps/api/scripts/export_openapi.py`，再执行`openapi-typescript ../api/openapi.json -o src/apis/generated.ts`。

旧 Vite 前端继续使用 `5173`，新前端使用 `5174`，迁移期间可以同时运行。
