# Agent Service

2026-10-14目录迁移：独立提取实现位于[src/agent/extraction_agent](./src/agent/extraction_agent/README.md)，共享服务包按当前目录改为src，API入口为src.main:app。算法、Prompt和expected不改，只调整引用；静态比对完成，未运行模型/业务测试。现有测试脚本参数不变，见[迁移记录](../../docs/service/agent/changelog/2026-10-14-extraction-agent-directory.md)。

2026-10-14本地ZH2.0.2按用户新口径精简规则，读取放线段两侧直接端子，业务端子排仅后处理映射，保留电流约束。用户自行测试，本轮未运行测试/模型，不写数据库或发布；见[记录](../../docs/service/agent/changelog/2026-10-14-zh-direct-terminals.md)。

2026-10-13 Supervisor 对话微调：专业电气图纸与线表助手增加 CHAT 路线，日常交流流式输出公开回答、不分派工作流；真实 PDF 才能进入类型确认及 Stage 1/2 提取。任务说明后展示卡片，保留纠错/规则修改确认和权限检查。SSE 只发送 `delta.content`，不发送模型内部推理；运行服务需加载新代码。见[对话交付](../../docs/service/agent/changelog/2026-10-13-supervisor-chat.md)。

2026-10-13 本地ZH2.0.1：方向缺失降级、原始引用解析、分支保留与端子身份校验；40项冒烟及7项接口/兼容回归通过。旧结果保留，尚未重跑真实模型，数据库与远端规则未变。见[变更记录](../../docs/service/agent/changelog/2026-10-13-zh-stage2-quality.md)。

本地测试入口：已有拆页/索引用`scripts/run_stage2_groups.py`，导出标准12列加两端坐标共14列，色标留空；新PDF用`scripts/run_page_workflow_extraction.py`自动拆页/分类/提取并输出含诊断列的table.xlsx。两者支持`--profile zh|abb|zh_gantry_reel`和`--model`，强制内存/本地资源，不写数据库/Storage；真实模型须`--allow-real-model`。命令和产物见[测试说明](../../docs/service/agent/local-stage2-group-test.md)。

2026-10-13 分支更新：提取改为 Stage 1 分类 + Stage 2 独立逐页 LangGraph，扫描/双图补全/保存形成闭环，删除独立 Stage 3 Agent 和全局补全阶段。实现见 [ADR-0014](../../docs/adr/0014-stage2-page-extraction-workflow.md) 与 [交付记录](../../docs/service/agent/changelog/2026-10-13-stage2-page-workflow.md)。本轮仅离线冒烟，不写真实数据库、不发布远端包、不重启服务；旧持久 run 只读，新 run 使用冻结 `page_extraction_v2` 工作流，真实库运行前需要未部署的新 migration。以下早期实施状态作为历史上下文。


规则库支持人工基于可用模板创建新 key，封存到私有 Bucket 后立即注册；所有登录用户共享读取，创建者确认删除后停用。要求 `AGENT_PROFILE_PACKAGES_ENABLED=true` 和既有 Supabase 配置。Profile API/新任务入口/首页检测刷新远端 active 集合并为同 key 选择最新版本；已冻结任务仍使用原 checksum。首次使用新增 adapter 需重载服务以加载新代码。见 [ADR-0012](../../docs/adr/0012-shared-ready-rule-library.md)。

2026-10-13 起，规则修改取消评测/二次审核：[ADR-0013](../../docs/adr/0013-confirmed-rule-update-without-evaluation.md)。聊天归因建议经一次“确认规则修改”后直接构建并启用包。已有候选由 `run_rule_release.py --candidate-id ... --user-id ...` 接续，输入“确认规则修改”即可；不调用模型评测，不需要 `AGENT_ALLOW_REAL_EVALUATION` 或脚本真实模型开关。需应用 migration `20261013000000` 并重载 API/Worker（不自动停止现有任务）。详见 [`纠错验收说明`](./agent_test/2.纠错agent/README.md)。

局部纠错现按用户要求改为原位更新（[ADR-0010](../../docs/adr/0010-in-place-confirmed-corrections.md)）：直接答案和 Stage 2/3 重识别在确认后保持连接 ID/线号不变，使用 revision/record_version 校验并保留 feedback 审计。完整提取仍产生代次。`20261011020000` 已在本地部署；现有服务需由用户重载才使用新提交代码，旧历史没有删除。见[实施记录](../../docs/service/agent/changelog/2026-10-11-in-place-corrections.md)。

纠错混合批次和 Profile 资源包的实现说明见[实施记录](../../docs/service/agent/changelog/2026-10-11-correction-packages-implementation.md)，本地 migration/ZH bootstrap 已部署，见[部署记录](../../docs/service/agent/changelog/2026-10-11-profile-package-deployment.md)。API/Worker 加载新代码前需要设置 `AGENT_PROFILE_PACKAGES_ENABLED=true`；现有服务未重启。本地 Profile 默认兼容模式不受影响。验收复用 test0；已有候选通过上述终端入口接续，不重复注错或执行纠错。

独立的 Python Agent API、运行底座和图纸 Profile 服务。默认监听 `8100`，不创建用户或直接覆盖生产线表。迁移期内部验收可登记已有 owner 的项目/源 PDF，并通过受控事务创建结果版本；不替代业务 Server 的浏览器鉴权入口。

当前已实现 Agent 服务骨架、Profile Router、ZH 三阶段本地提取链路，以及 Run/Worker、Supervisor、Correction 和 Improvement 的受控执行基座：

阶段 0 的纯 HTTP 终端验收见 [`agent_test/0.detection_test/README.md`](./agent_test/0.detection_test/README.md)。Supervisor 现具备进程内短期会话记忆，支持上传会话 PDF、只识别类型、等待用户确认，以及确认后追问当前类型；长期记忆和跨进程对话恢复尚未实现。

Gate A 的正式 Supabase FULL_EXTRACTION 使用 protocol 2：各阶段提交后从数据库重新加载，上游项/输入固定，支持过期 RUNNING 接管、fencing、空缓存恢复和结果 receipt 驱动的幂等收尾。旧 run/旧脚本保留 protocol 1；本地三阶段 CLI 仍不落库。实际验证与命令见 [Gate A 记录](../../docs/service/agent/changelog/2026-10-10-gate-a-implementation.md)。

Gate B 内部上传/确认/Worker/SSE 链路已接通，见 [阶段 1 HTTP 验收说明](./agent_test/1.3stage/README.md)。`/v1/imports` 要求已有 Supabase Auth 用户 UUID、内部 Bearer 和 Idempotency-Key；确认后原子登记带冻结 Profile 的持久 run。项目树只读 published snapshot，结果按固定版本分页，SSE 支持 Last-Event-ID。真实模型字段准确率和 Web/JWT 代理尚未验收。本地已应用 `20261011000000` 原子入队 migration，部署其他库时须应用新增 migration。

- FastAPI 应用、配置、日志和健康检查；
- Run/Event/Proposal/Correction/Supervisor 公共领域契约；
- Model Gateway、Tool Registry、Context、Checkpoint 和 Trace 最小 Harness；
- Profile Registry、版本化 ZH Profile 和动态资源绑定；
- 只读取 PDF 物理首页的 Profile Router、人工确认和动态 ProfileBinding。
- Stage 1 `PageClassifierAgent` 与 Stage 2 页工作流；`PageScannerAgent` 提供初扫及内部补全操作，保持 Pydantic 契约；
- ZH `ZhVlmExtractionStageAdapter` 通过 Agent 自己的 OpenAI-compatible Model Gateway 调用模型，分类、初扫和内部补全都发送真实图片 Few-shot；
- 文档 Graph 位于 `graphs/document_extraction`；PDF/checkpoint/JSON/XLS(X) 位于 `infrastructure/document`；端子、方向、电流、引用解析和导出字段通过 `profiles/zh` 策略注入；`zh_workflow` 兼容目录已删除；
- `scripts/run_page_workflow_extraction.py` 执行分类及逐页闭环提取，输出两阶段 JSON、完成页 checkpoint 和 XLSX，不写数据库；
- Supervisor 意图 Graph、Workflow Registry、首页 Profile Detection 内部工具，以及按项目/工作区/业务页码/线号/端子检索的受控结果工具；
- 三态 `is_cross_page` 纠错路由、Correction proposal、用户确认后的 Supabase 原子版本提交和 accepted-feedback Improvement 触发；
- Improvement Diagnoser 的脱敏原因/建议事件、显式授权后的 Profile Patch Builder、Evaluation Judge、离线 Eval Runner、Profile Sandbox 与确定性 Release Gate。

M4 的真实 VLM 首页识别评测和 ZH 固定案例字段级回归仍未执行。Agent HTTP 服务提供健康检查、Profile、Run 控制、事件查询/SSE、Proposal 查询、Supervisor 回合及候选审核路由。默认 `memory` 模式用于离线测试；设置 `AGENT_PERSISTENCE_BACKEND=supabase` 与 `AGENT_CHECKPOINT_BACKEND=supabase` 后，Run/Event/Artifact/Proposal/Checkpoint、源 PDF 和任务队列持久化到 Supabase，队列通过数据库租约支持独立 Worker 跨进程消费。`AGENT_INLINE_WORKER=true` 仅用于同进程开发。HTTP Run 只接受已登记的 source-document 对象引用，不接受任意本地路径。

Supabase 模式下，完整提取 Proposal 会原子写入规范化结果版本；source document 和 Correction drawing 会从私有 Bucket 下载并校验或重新物化。受控结果工具支持多条件查询、持久 Correction bundle、乐观版本提交和 accepted feedback；Profile candidate、release gate、eval、状态审计和模型 Trace 也会持久化。Stage 1/2/3 本身仍只返回结构化候选，只有完整提取持久步骤或用户明确确认修订后才调用受控提交 RPC。

ABB Profile 1.1.2 使用独立三阶段 Prompt，各阶段仅一案例：Stage 1 原页 205、Stage 2 原页 205（示范 Q4 跨页连接）、Stage 3 原页 205+目标页 241。资源已上传私有 `agent-profile-assets` 并读回校验；`abb_native` VLM adapter、Sheet/Cont 页面索引、跨页引用与确定性策略已注册，全量 Graph 可执行。真实模型字段级质量仍待人工验收。见 [ABB 资源说明](src/agent/extraction_agent/prompts/abb/README.md)。

上传可用规则资源包（不覆盖不可变旧包；使用已有 Auth 用户 UUID）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/upload_profile_package.py abb `
  --user-id "<已有 Auth 用户 UUID>"
```

脚本上传后下载全部资源并校验 checksum；三阶段 schema、manifest 和路径会在打包时校验。样例图片副本可通过 `services/agent/scripts/prepare_abb_example_images.py` 复现。

## 启动

以下命令使用 Windows PowerShell，从仓库根目录执行；克隆路径不同时调整 `Set-Location`。需要 Python 3.10+。完整本地联调按 Agent（8100）→ [Server/API（8000）](../server/README.md#启动) → [Web（5174）](../../apps/web/README.md#启动) 的顺序，在独立终端启动。

首次准备虚拟环境、Agent 包及其运行/开发依赖，已有环境和配置时保留：

```powershell
Set-Location E:\project\zhenghua_test
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e "services/agent[dev]"
if (-not (Test-Path services\agent\.env)) { Copy-Item services\agent\.env.example services\agent\.env }
```

编辑 `services/agent/.env`，填写模型地址、`AGENT_MODEL_API_KEY` 和 `AGENT_DEFAULT_MODEL`，确认 `AGENT_INTERNAL_TOKEN` 与 Server 一致。`AGENT_MODEL_BASE_URL` 填服务根地址（通常以 `/v1` 结尾），也可以直接填写完整的 Chat Completions 地址到 `AGENT_MODEL_CHAT_COMPLETIONS_URL`。

Agent 只读取 `services/agent/.env`，不会加载仓库根目录或 `backend/.env`。运行进程中显式设置的环境变量优先；模型配置兼容旧 `VLM_*`，Supabase 凭据兼容旧 `SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY`。旧 `SUPABASE_STORAGE_BUCKET=images` 不会被继承，Agent 新链路默认使用私有 `project-assets`。`AGENT_INLINE_WORKER` 只适用于同进程开发测试。

生产持久模式至少需要：

```dotenv
AGENT_PERSISTENCE_BACKEND=supabase
AGENT_CHECKPOINT_BACKEND=supabase
AGENT_SUPABASE_URL=http://127.0.0.1:54321
AGENT_SUPABASE_SERVICE_ROLE_KEY=...
AGENT_SUPABASE_STORAGE_BUCKET=project-assets
```

不要沿用旧公开 `images` Bucket。新链路的原始 PDF、页面图片和阶段产物必须写入 migration 创建的私有 `project-assets`；service-role key 只允许存在于 Server/Agent 进程环境中。

启动 Agent API 和本地同进程 Worker：

```powershell
Set-Location E:\project\zhenghua_test
$env:AGENT_INLINE_WORKER="true"
.\.venv\Scripts\python.exe -m uvicorn src.main:app `
  --app-dir services/agent `
  --host 127.0.0.1 `
  --port 8100
```

`AGENT_INLINE_WORKER` 默认是 `false`；上面的进程环境变量开启本地开发 Worker，否则只启动 HTTP API，排队任务需要其他 Worker 消费。使用 `memory` 队列时 API 与 Worker 必须在同一进程；真实工作台上传和持久提取需要上面的 Supabase 配置、已应用的所需 migration 和可用私有 Bucket。该开发命令沿用 `.env` 中的持久化配置，不会将 Supabase 模式切换为内存模式。仅本地图纸、不落库的测试请使用下方独立 CLI 或[分组测试说明](../../docs/service/agent/local-stage2-group-test.md)。

接口文档为 `http://127.0.0.1:8100/docs`。启动后可在另一终端检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health/live
Invoke-RestMethod http://127.0.0.1:8100/health/ready
```

停止当前开发服务使用 `Ctrl+C`。处理任务期间避免启用自动 reload，以免中断模型调用及进程内会话。

未配置模型时，`/health/live` 仍返回 `200`，`/health/ready` 返回 `503` 并列出未就绪项。

```text
GET http://127.0.0.1:8100/health/live
GET http://127.0.0.1:8100/health/ready
GET http://127.0.0.1:8100/v1/profiles
GET http://127.0.0.1:8100/v1/profiles/zh/versions/1.0.0/rules
POST http://127.0.0.1:8100/v1/runs
GET  http://127.0.0.1:8100/v1/runs/{agent_run_id}/events/stream
POST http://127.0.0.1:8100/v1/supervisor/turns
```

## 测试

默认测试不调用真实 VLM：

```powershell
$env:PYTHONPATH="services/agent;."
.\.venv\Scripts\python.exe -m pytest services\agent\tests
```

本地 Supabase 启动并应用 migration 后，可运行真实持久化冒烟。脚本会创建临时用户和项目，验证完成后清理，不调用 VLM：

```powershell
$env:PYTHONPATH="services/agent"
$env:AGENT_SUPABASE_URL="http://127.0.0.1:54321"
$env:AGENT_SUPABASE_SERVICE_ROLE_KEY="..."
$env:AGENT_SUPABASE_ANON_KEY="..."
$env:AGENT_SUPABASE_STORAGE_BUCKET="project-assets"
.\.venv\Scripts\python.exe services\agent\scripts\verify_supabase_production_foundation.py
```

该冒烟覆盖私有 Storage、签名 URL、RLS、PDF checksum、页面发布、租约队列、并发事件序号、Artifact、Proposal、Checkpoint 乐观锁与从 1000 开始的并发线号分配。

完整数据库工作流验证不调用 VLM，覆盖提取落库、结果查询、纠错确认、新版本、accepted feedback、Trace、候选、评测、门禁和审计：

```powershell
$env:PYTHONPATH="services/agent"
.\.venv\Scripts\python.exe services\agent\scripts\verify_supabase_agent_database_workflows.py
```

若当前环境没有安装可选开发依赖 `pytest`，可用 `unittest` 执行迁移相关回归：

```powershell
$env:PYTHONPATH="services/agent;."
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_agent_settings.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_atomic_checkpoint.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_native_vlm_stages.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\integration -p "test_standalone_three_stage_workflow.py"
```

## 三阶段提取

Stage 2/3 会保留 manifest 中的图像 Few-shot，但发送给模型前会将最长边超过 `AGENT_MODEL_FEWSHOT_MAX_IMAGE_SIDE` 的样例图按 2 的幂次缩小，默认最长边不超过 1800 像素。磁盘中的案例图片和待提取原图不变；该配置只控制 Few-shot 请求图像大小。

Stage 2 的完整入口为 `graphs/document_extraction/page_extraction.py` 中的 `run_page_extraction`，可包装为主 Agent 的工具/子 Agent；初扫模型节点 `run_page_scan` 不是完整提取入口。文档级入口为 `application/page_workflow_extraction.py::run_page_workflow_extraction`。

流程：分类全部页并建立索引 → 本页初扫起点 → 内部引用规划 → 来源图/唯一目标图定向补全 → 校验 → 保存完成页 → 下一页。不扫描目标页其他连接，不递归扩张引用。跨页无法确认时终点 null、needs_review；配置/权限/持久化失败仍停止，不把写入失败当作完成。

ZH 2.0.0 取消 XA/XD 白名单与强制换向，按实际放线标记/路径和箭头判断来源；无箭头保留模型证据，方向不确定待复核。实际端子标识保留，端子排明确值优先，否则按已知端子映射，无法映射留空。PE 不自动填颜色/未确认终点，业务代号不凭常识转换。新样例有 C01 正例、C03 接收端局部负例、C01→C02 双图补全；旧白名单 expected 归档为 legacy，真实模型与人工基线验收尚未完成。

本地完成页存于 `agent/completed-pages/<physical-page>.json`，输入/Profile/图片指纹变化会拒绝旧缓存；恢复跳过完成页。数据库模式初扫/补全模型缓存与完成页 StageItem 分离，最终业务版本仍通过 Server 原子提交。`supabase/migrations/20261013010000_stage2_page_workflow.sql` 只新增冻结工作流前驱/完成页事实校验，未执行；没有修改已应用迁移。已有旧 run 不续跑混合阶段，应新建 run；既有项目不重绑 Profile。

离线冒烟（禁止网络请求，不调用模型/数据库）：

```powershell
.\.venv\Scripts\python.exe -m pytest services/agent/tests/smoke/test_stage2_page_workflow.py -q
```

真实模型 CLI 需要显式授权开关，以下命令不属于本轮验证：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_page_workflow_extraction.py `
  "case/example.pdf" --output-dir "runs/page-extraction" --allow-real-model
```

`01_page_classification` 保存分类/索引，`02_page_scan` 保存扫描/内部补全/最终表格，最终预览为 `02_page_scan/table.xlsx` 和根目录 `table.xlsx`，不再创建 `03_cross_page_completion`。历史阶段枚举、CorrectionAction、`cross_page_prompt` / `stage3_cases` 资源标识保留用于读取旧数据，不代表新运行有独立 Stage 3。ABB Prompt 未调整，内部操作保持其原单目标查询图片契约。

## M4 Profile 首页识别

M4 只读取 PDF 物理首页。默认测试使用 Fake VLM；真实模型识别必须显式执行：

```powershell
$env:AGENT_MODEL_BASE_URL="http://your-model-host/v1"
$env:AGENT_MODEL_API_KEY="..."
$env:AGENT_DEFAULT_MODEL="your-vlm"

.\.venv\Scripts\python.exe services\agent\scripts\test_profile_detection.py `
  "case\1002001641 PERU TPP 1 STS.pdf"
```

无法自动识别或识别到 experimental Profile 时，结果为 `WAITING_INPUT`。可在测试中模拟用户确认：

```powershell
.\.venv\Scripts\python.exe services\agent\scripts\test_profile_detection.py `
  "case\abb\ABB原理图说明.pdf" `
  --confirm-profile abb
```

确认结果生成不可变 `ProfileBinding`，其中包含 Profile 版本、checksum、公开规则和三阶段动态资源映射。

## 边界

- `src.domain` 不依赖 FastAPI、数据库 SDK 或模型供应商。
- 新原生子 Agent 通过 Harness 调用模型与工具；`legacy_zh_adapter.py` 与 `legacy_zh_stages.py` 仅保留旧 Agent 调用方的兼容入口，不导入或执行旧 `backend` 实现。
- `LegacyZhExtractionAdapter` 只返回候选结果，不提交生产数据。
- `LegacyZhStageAdapter` 只执行单阶段 VLM 调用并返回候选 Schema，不负责索引、最终校验或生产数据写入。
- ABB 当前可作为新任务 Profile；真实模型准确率基线仍未完成，验收前应保留人工确认和 `needs_review` 路径。
- Supabase 模式已持久化 Run/Event/Artifact/Proposal/Checkpoint/Trace、源 PDF、页面图片、规范化结果版本、Correction/accepted feedback、候选、评测、门禁审计和租约队列。启用远端资源包后，候选评测从冻结 Bucket 包读取，人工审核/发布通过服务端 receipt；隔离沙箱不直接覆盖生产 Profile。Bucket 发布执行器已实现，真实模型评测和发布验收待执行。
