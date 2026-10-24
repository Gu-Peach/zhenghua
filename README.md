# 振华重工放线表提取系统

从电气原理图 PDF 提取结构化放线表，支持项目/图纸目录、来源定位、人工修订、重扫候选、规则配置和 XLSX 导出。业务事实保存在 Supabase PostgreSQL，PDF、图片和规则包保存在私有 Storage。

本文按当前源码说明本地安装和启动，更新于 **2026-10-24**。命令使用 **Windows PowerShell**，除特别说明外均在仓库根目录执行。实际克隆位置不同时替换 `E:\project\zhenghua_test`。

## 1. 服务和目录

| 服务 | 代码位置 | 本地地址 | 作用 |
| --- | --- | --- | --- |
| Web | `apps/web` | http://localhost:5174 | React + Vite + TypeScript 工作台 |
| 业务 API | `apps/api/src/main.py`、`services/server` | http://127.0.0.1:8000 | 登录、JWT 校验、业务事务、Agent 代理 |
| Agent API | `services/agent/src/extraction_main.py` | http://127.0.0.1:8100 | Explain、Profile、主助手共享 HTTP 宿主 |
| Agent Worker | `services/agent/src/agent/extraction_agent/application/incremental_worker.py` | 无 HTTP 端口 | 消费提取及重扫任务，保存进度和结果 |
| Supabase API | Docker / Supabase CLI | http://127.0.0.1:54321 | Auth、PostgREST、Storage |
| PostgreSQL | Docker / Supabase CLI | `127.0.0.1:54322` | 数据库连接端口 |
| Supabase Studio | Docker / Supabase CLI | http://127.0.0.1:54323 | SQL、用户和 Storage 管理 |

Supabase 地址以 `supabase status` 输出为准。浏览器通过同源 `/api` 访问业务 API，Vite 已配置代理到 8000；浏览器不直连 Agent，也不持有服务端密钥。

当前迁移目录为 [`supabase/migrations`](supabase/migrations)，尚未迁至规划中的 `infra/supabase`。当前业务采用三张核心表及 Agent/会话辅助表；旧 `wiring_tables` 已被后续迁移移除。本地 `agent_test` 属于实验副本，不是工作台服务入口。

## 2. 安装依赖

需要 Python **3.10+**、Node.js **22.12+**、Corepack、项目固定的 **pnpm 10.33.0**、Docker Desktop 和 Supabase CLI。锁文件中 Vite 的 Node 要求为 `^20.19.0 || >=22.12.0`。Docker Desktop 需启用 WSL 2 / Linux containers，并启动 Docker Engine。

Windows 已有 Scoop 时可安装 Supabase CLI；其他方式见 [Supabase 官方安装说明](https://supabase.com/docs/guides/local-development/cli/getting-started)：

```powershell
scoop bucket add supabase https://github.com/supabase/scoop-bucket.git
scoop install supabase
docker version
supabase --version
node --version
python --version
```

如果没有 `corepack` 命令，先执行 `npm install --global corepack`。以下命令无需激活 Python 虚拟环境：

```powershell
Set-Location E:\project\zhenghua_test
corepack pnpm install --frozen-lockfile
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e services/server -e services/agent

if (-not (Test-Path services\server\.env)) {
    Copy-Item services\server\.env.example services\server\.env
}
if (-not (Test-Path services\agent\.env)) {
    Copy-Item services\agent\.env.example services\agent\.env
}
if (-not (Test-Path apps\web\.env.local)) {
    Copy-Item apps\web\.env.example apps\web\.env.local
}
```

## 3. 数据库安装、启动与建表

### 3.1 全新本地环境

必须安装完整 Supabase 栈；单独安装 PostgreSQL 不会提供本项目使用的 `auth.users`、`auth.uid()`、`storage.buckets`、REST 和登录服务。

以下步骤用于**全新本地实例**。若机器上已有此项目的数据库，请先使用 3.2 节核对，不能将已有库当作空库重新初始化。仓库未提交 `supabase/config.toml`，首次生成本地配置，已有配置则保留：

```powershell
Set-Location E:\project\zhenghua_test
if (-not (Test-Path supabase\config.toml)) { supabase init }
```

启动前检查生成的 `supabase/config.toml`：

- `project_id` 是本机实例标识，不要与已有其他项目共用标识或端口。
- `[auth]` 的 `site_url` 可设为 `http://localhost:5174`。
- `[storage]` 的 `file_size_limit` 可设为 `"500MiB"`，与 bucket 上限配合；业务 API 对原 PDF 仍限制 200 MiB。
- 若生成配置启用了 seed、但没有 `supabase/seed.sql`，将 `[db.seed]` 的 `enabled` 设为 `false`。本文通过 Studio 创建用户，通过独立命令发布规则。

```powershell
supabase start
supabase status
```

首次启动会下载镜像、创建 Supabase 内置 schema，并应用仓库迁移，无需另装 PostgreSQL 服务。详见 [官方本地开发说明](https://supabase.com/docs/guides/local-development/cli/getting-started)。

项目提供统一的**建表/迁移入口脚本**，内部调用 CLI、按迁移历史执行尚未应用的 SQL，不复制另一套表结构：

```powershell
# 先预览尚未应用的迁移，不写库
.\supabase\scripts\create_tables.ps1
# 全新实例应用剩余迁移；若 start 已应用完整历史，此步没有待执行项
.\supabase\scripts\create_tables.ps1 -Apply
```

目前完整历史从 `20260918000000_create_wiring_tables.sql` 到 `20261020020000_bulk_connection_review.sql`。必须按时间顺序使用完整迁移目录，不能只执行三张核心表的 CREATE TABLE：应用还需要事务函数、索引、触发器、RLS、Agent 任务和助手表。

**历史中的 `20261014010000_retire_old_extraction_business_tables.sql` 会永久删除旧业务表及其中的数据。** 空库可顺序重放；有旧数据的库必须先备份并评审迁移，不可直接套用全新初始化流程。

### 3.2 已有实例的启动和升级

使用原来的 `supabase/config.toml`、`project_id` 和工作目录。若原配置在其他目录，先切到原目录启动，不能重新 `supabase init` 冒充原实例。

```powershell
supabase start
supabase status
supabase migration list --local
```

确认当前目录/配置对应目标实例后，在仓库根目录执行 `create_tables.ps1` 查看待执行清单。备份并评审后才使用 `-Apply`；脚本固定操作本地实例，不会自动连接云端。底层命令为 `supabase db push --local --dry-run` 与 `supabase migration up --local`，见 [CLI 参考](https://supabase.com/docs/reference/cli/supabase-db-push)。

若曾通过 SQL Editor 手工部署，表已存在但迁移历史缺失，应先核对并补正迁移历史；不要反复运行 CREATE TABLE 或无核对地标记迁移完成。**`supabase db reset` 会重建数据库，不是日常启动命令。**

日常停止用 `supabase stop`，保留数据供下次启动，不加 `--no-backup`。应用进程分别在自己的终端按 `Ctrl+C` 停止。

### 3.3 表结构及创建脚本

| 对象 | 用途 |
| --- | --- |
| `extraction_profiles` | 已发布规则标识、版本、checksum、Storage 引用、创建者 |
| `extraction_projects` | 所有者、项目、原 PDF 引用、JSON 图纸目录和处理状态 |
| `extraction_connection_rows` | 批次线表、起终点、业务页号/PDF 物理页号、坐标、复核及行版本 |
| `agent_runs`、`agent_events`、`agent_artifacts`、`agent_checkpoints`、`agent_run_queue`、`agent_traces` | 持久任务、进度、产物、checkpoint、队列及诊断 |
| `connection_edit_proposals`、`connection_rescan_runs`、`connection_rescan_assets` | 修改方案、重扫任务和附件 |
| `assistant_conversations`、`assistant_turns`、`assistant_actions`、`assistant_attachments` | 主助手会话、轮次、工具动作及附件 |
| `profile_asset_gc`、`assistant_asset_gc` | 规则包/会话附件的持久清理队列 |

以下 SQL 可以直接审阅，但有前序依赖，完整安装请使用上方迁移入口：

- [三张核心业务表](supabase/migrations/20261014000000_create_simple_extraction_business_tables.sql)
- [Agent 运行表和 project-assets bucket](supabase/migrations/20261009020000_create_project_assets_and_agent_runtime.sql)、[Agent 队列](supabase/migrations/20261009030000_add_agent_queue_and_atomic_runtime_functions.sql)、[Agent traces](supabase/migrations/20261009050000_persist_agent_results_and_improvement.sql)
- [增量提取事务及 ZIP MIME 支持](supabase/migrations/20261016020000_incremental_extraction.sql)
- [规则发布](supabase/migrations/20261017010000_profile_wizard_publication.sql)、[规则包清理](supabase/migrations/20261018010000_profile_editing_replacement.sql)
- [修改方案](supabase/migrations/20261018020000_explain_connection_edits.sql)、[重扫](supabase/migrations/20261018050000_explain_rescan.sql)
- [主助手](supabase/migrations/20261019020000_main_assistant.sql)、[会话附件清理](supabase/migrations/20261019050000_assistant_conversation_deletion.sql)
- [独立 bucket 创建脚本](supabase/scripts/create_buckets.sql)、[只读安装检查脚本](supabase/scripts/verify_setup.sql)

### 3.4 创建 bucket 和检查安装

完整迁移已经创建所需 bucket。单独提供的 `create_buckets.sql` 可在 **Studio → SQL Editor** 中粘贴执行，补建缺失的私有 bucket；它不覆盖已有配置、不创建公开读写策略。已有 bucket 的权限/MIME 不符时会报错，需管理员评审后修正。

| Bucket | 可见性 | 用途 |
| --- | --- | --- |
| `project-assets` | 私有 | 当前 PDF、图纸、阶段产物、已发布规则 ZIP、辅助附件等 |
| `agent-profile-assets` | 私有 | 保留的旧 Agent Profile 资源桶，当前规则发布使用 `project-assets` |
| `images` | 历史公开桶 | 早期迁移创建，当前工作台不使用；新脚本不会额外创建它 |

`project-assets` 默认允许 PDF、PNG、JPEG、JSON、XLSX、ZIP，文件上限 524288000 字节。Storage 服务全局上限同样生效。私有文件经业务 API 授权后生成短期签名 URL；不要为了预览把 bucket 改成公开。

执行 `verify_setup.sql` 检查关键表、RLS、内部 RPC 和 bucket。脚本只读且不返回用户数据；`present` / `rls_enabled` / `configuration_ok` 应为 `true`。`recorded_migration_count` 是 CLI 历史记录数，不等同于业务验收。

如已安装 `psql`，也可使用管理员连接执行（按 `supabase status` 实际地址调整，密码通过提示输入）：

```powershell
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -W -v ON_ERROR_STOP=1 -f supabase/scripts/create_buckets.sql
psql -h 127.0.0.1 -p 54322 -U postgres -d postgres -W -v ON_ERROR_STOP=1 -f supabase/scripts/verify_setup.sql
```

## 4. 配置服务端和前端

### 4.1 业务 API：`services/server/.env`

```dotenv
SERVER_SUPABASE_URL=http://127.0.0.1:54321
SERVER_SUPABASE_SERVICE_ROLE_KEY=<本实例的 service_role key>
SERVER_AGENT_URL=http://127.0.0.1:8100
AGENT_INTERNAL_TOKEN=<自行生成的内部令牌，与 Agent 保持一致>
SERVER_WEB_ORIGIN=http://localhost:5174
SERVER_DATABASE_URL=
```

本地密钥从 `supabase status` 获取。当前三表工作台通过 Supabase REST/RPC 事务读写，常规启动不要求填写 `SERVER_DATABASE_URL`，也无需旧的 `run_local_api.py` 直连启动器。

### 4.2 Agent API 和 Worker：`services/agent/.env`

保留 `.env.example` 其他默认值，至少填写/修改：

```dotenv
AGENT_ENV=development
AGENT_INTERNAL_TOKEN=<与 services/server/.env 相同的令牌>
AGENT_SERVER_BASE_URL=http://127.0.0.1:8000
AGENT_SUPABASE_URL=http://127.0.0.1:54321
AGENT_SUPABASE_SERVICE_ROLE_KEY=<与 Server 指向同一实例的 service_role key>
AGENT_SUPABASE_STORAGE_BUCKET=project-assets
AGENT_PERSISTENCE_BACKEND=supabase
AGENT_CHECKPOINT_BACKEND=supabase
AGENT_PROFILE_PACKAGES_ENABLED=true
AGENT_INLINE_WORKER=false
AGENT_MODEL_BASE_URL=https://your-model-host/v1
AGENT_MODEL_CHAT_COMPLETIONS_URL=
AGENT_MODEL_API_KEY=<模型服务密钥>
AGENT_DEFAULT_MODEL=<支持图片输入的模型名称>
AGENT_MODEL_JSON_MODE=false
```

模型端点需兼容 Chat Completions 并支持图片输入；也可将完整 URL 填入 `AGENT_MODEL_CHAT_COMPLETIONS_URL`。只在供应方支持时启用 JSON mode。真实上传提取、重扫和聊天会调用配置的模型，可能产生费用。

Agent 只加载 `services/agent/.env`，进程环境变量优先。Server 优先使用自己的 `SERVER_*` 配置，不能假定自动继承 `AGENT_SUPABASE_*`。所有密钥仅保存在服务端 `.env`，不得提交 Git 或写入 `VITE_*`。

### 4.3 Web：`apps/web/.env.local`

```dotenv
VITE_API_BASE_URL=
```

留空使用 Vite 同源代理。浏览器统一访问 `http://localhost:5174`；改域名/端口时同步代理及 Server 允许的 Origin，避免刷新 Cookie 失效。修改 `.env` 后重启相应进程。

## 5. 启动前后端和 Agent

数据库就绪后，分别打开四个 PowerShell 终端。建议顺序：**业务 API → Agent API → Worker → Web**。

### 终端一：业务 API（8000）

```powershell
Set-Location E:\project\zhenghua_test
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

接口文档：http://127.0.0.1:8000/docs；健康接口：http://127.0.0.1:8000/health。

### 终端二：Agent API（8100）

```powershell
Set-Location E:\project\zhenghua_test
$env:AGENT_INLINE_WORKER = "false"
.\.venv\Scripts\python.exe -m uvicorn src.extraction_main:app --app-dir services/agent --host 127.0.0.1 --port 8100
```

当前工作台使用 **`src.extraction_main:app`**；旧文档中的 `src.main:app` 是旧控制面入口。接口文档：http://127.0.0.1:8100/docs。

### 终端三：独立 Worker（无端口）

```powershell
Set-Location E:\project\zhenghua_test\services\agent
..\..\.venv\Scripts\python.exe -m src.agent.extraction_agent.application.incremental_worker
```

此进程同时处理普通提取和重扫。只启动 8100、未启动 Worker 时，任务会排队；只启动 Worker 则无法提供聊天 HTTP 服务。开发时可把终端二的 `AGENT_INLINE_WORKER` 设为 `true`，让 8100 同进程启动 Worker，此时省略终端三。两种方式选一种。

### 终端四：Web（5174）

```powershell
Set-Location E:\project\zhenghua_test
corepack pnpm dev:web
```

打开 http://localhost:5174/login。端口占用时 Vite 会直接报错，不会自动换端口。

## 6. 首次登录和规则初始化

1. 在 Studio 的 **Authentication → Users** 创建邮箱/密码用户，并确认邮箱。当前 Web 提供登录入口，不会自动创建默认账号；不要直接向 `auth.users` 手工拼密码记录。
2. 用该邮箱/密码登录 Web。首次没有项目属于正常空态。
3. 新库规则目录也是空的。当前上传列表只显示数据库内已发布的完整 Storage 包，本地存在 Prompt 目录不代表它已经可选。

可通过“用户菜单 → 智能体中心 → Extraction Agent”创建规则，逐阶段确认后手动发布；也可由管理员把仓库随附规则发布到新实例：

```powershell
Set-Location E:\project\zhenghua_test
# 替换为 Studio 中刚创建的用户 UUID，不是邮箱或数据库密码
$profileOwnerId = "<Auth 用户 UUID>"
# 打包并检查目标库，不上传；需要数据库连接，不调用模型
.\.venv\Scripts\python.exe services/agent/scripts/bootstrap_database_profiles.py --owner-id $profileOwnerId
# 确认预检通过后上传规则包并登记目录
.\.venv\Scripts\python.exe services/agent/scripts/bootstrap_database_profiles.py --owner-id $profileOwnerId --apply
```

脚本固定发布 `zh 2.3.0`、`abb 1.3.1`、`zh_gantry_reel 0.2.1`，从正式 Profile 资源打包，**不发布 `agent_test` 实验副本**。同版本内容不同或属于其他创建者时拒绝。它不是任意 Profile 升级器，已有环境不要用它覆盖历史版本。预检/上传记录位于被忽略的 `.runtime/profile-catalog-upload`。

刷新上传对话框后选择规则和 PDF。上传成功自动入队，Worker 逐步保存目录与线表；模型结果仍需人工复核。重扫/修改候选须由用户确认后才写入正式线表。

## 7. 检查和排错

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8100/health
```

8100 返回 `service: independent_agents`。独立 Worker 模式下，`worker_running: false` 是预期结果，仅表示 HTTP 进程没有内嵌 Worker，不反映独立 Worker 状态。健康接口不是数据库/模型验收；还需检查 Worker 日志、登录及数据库检查结果。

| 现象 | 检查位置 |
| --- | --- |
| Docker 连接失败 | Docker Desktop、Linux containers/WSL 2 是否运行 |
| 登录失败或刷新退出 | Auth 用户/邮箱确认、Supabase 地址和密钥、Origin/同源 Cookie |
| 上传没有规则可选 | `extraction_profiles` 是否有完整已发布的 `storage://project-assets/...zip` |
| 上传一直排队 | Worker 日志、是否连接与 Server 相同的 Supabase |
| Worker RPC 404 / 表不存在 | 迁移历史和 `verify_setup.sql`；仅建三张表不足以运行 |
| Explain/主助手连接失败 | 8100 是否使用 `src.extraction_main:app`、内部令牌和回调地址 |
| Storage 拒绝 ZIP 或大文件 | bucket MIME、文件上限及 `[storage]` 全局上限 |
| 更新后仍缺接口 | 重启对应 API/Agent/Worker；刷新 Web 不会重载 Python |

开发检查命令：

```powershell
corepack pnpm typecheck:web
corepack pnpm lint:web
corepack pnpm build:web
.\.venv\Scripts\python.exe -m pip install -e 'services/server[test]' -e 'services/agent[dev]'
.\.venv\Scripts\python.exe -m pytest services/server/tests -q
Push-Location services/agent
try { ..\..\.venv\Scripts\python.exe -m pytest } finally { Pop-Location }
```

数据库/真实模型集成测试有独立显式开关，不属于默认离线测试。生产部署还需 HTTPS、同源反向代理、服务守护、备份及密钥管理；`vite preview` 仅用于预览构建产物。

## 8. 更多文档与本次验证范围

- [文档索引](docs/README.md)、[产品需求](docs/frontend.md)、[重构方案](docs/refactor-plan.md)
- [数据库脚本说明](supabase/README.md)
- [Web](apps/web/README.md)、[业务 API](apps/api/README.md)、[Server](services/server/README.md)、[Agent](services/agent/README.md)
- [开发路线](docs/roadmap.md)、[TODO](docs/TODO.md)、[变更记录](docs/changelog/README.md)

部分模块 README 包含历史阶段记录，当前完整启动流程以本文及最新源码为准。本次核对了服务入口、配置、迁移引用和 CLI 参数；未修改实际数据库或启动模型任务。由于当前 Docker daemon 不可连接，尚未完成全新 Supabase 安装和空库迁移的实际端到端验证。
