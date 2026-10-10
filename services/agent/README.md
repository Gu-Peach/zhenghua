# Agent Service

独立的 Python Agent API、运行底座和图纸 Profile 服务。默认监听 `8100`，不管理用户、项目权限或生产线表，也不会直接覆盖业务 Server 数据。

当前已实现 Agent 服务骨架、Profile Router、ZH 三阶段本地提取链路，以及 Run/Worker、Supervisor、Correction 和 Improvement 的受控执行基座：

阶段 0 的纯 HTTP 终端验收见 [`agent_test/0.detection_test/README.md`](./agent_test/0.detection_test/README.md)。Supervisor 现具备进程内短期会话记忆，支持上传会话 PDF、只识别类型、等待用户确认，以及确认后追问当前类型；长期记忆和跨进程对话恢复尚未实现。

- FastAPI 应用、配置、日志和健康检查；
- Run/Event/Proposal/Correction/Supervisor 公共领域契约；
- Model Gateway、Tool Registry、Context、Checkpoint 和 Trace 最小 Harness；
- Profile Registry、版本化 ZH Profile 和动态资源绑定；
- 只读取 PDF 物理首页的 Profile Router、人工确认和动态 ProfileBinding。
- Stage 1 `PageClassifierAgent`、Stage 2 `PageScannerAgent`、Stage 3 `CrossPageResolverAgent`，各自有独立 Pydantic 契约和 LangGraph 子图；
- ZH `ZhVlmExtractionStageAdapter` 通过 Agent 自己的 OpenAI-compatible Model Gateway 调用模型，三阶段调用都发送真实图片 Few-shot；
- 文档 Graph 位于 `graphs/document_extraction`；PDF/checkpoint/JSON/XLS(X) 位于 `infrastructure/document`；端子、方向、电流、引用解析和导出字段通过 `profiles/zh` 策略注入；`zh_workflow` 兼容目录已删除；
- `scripts/run_three_stage_extraction.py` 串联三个新 LangGraph 子图与迁入的确定性工作流，输出三阶段 JSON 和标准 XLSX，不写数据库；
- Supervisor 意图 Graph、Workflow Registry、首页 Profile Detection 内部工具，以及按项目/工作区/业务页码/线号/端子检索的受控结果工具；
- 三态 `is_cross_page` 纠错路由、Correction proposal、用户确认后的 Supabase 原子版本提交和 accepted-feedback Improvement 触发；
- Improvement Diagnoser 的脱敏原因/建议事件、显式授权后的 Profile Patch Builder、Evaluation Judge、离线 Eval Runner、Profile Sandbox 与确定性 Release Gate。

M4 的真实 VLM 首页识别评测和 ZH 固定案例字段级回归仍未执行。Agent HTTP 服务提供健康检查、Profile、Run 控制、事件查询/SSE、Proposal 查询、Supervisor 回合及候选审核路由。默认 `memory` 模式用于离线测试；设置 `AGENT_PERSISTENCE_BACKEND=supabase` 与 `AGENT_CHECKPOINT_BACKEND=supabase` 后，Run/Event/Artifact/Proposal/Checkpoint、源 PDF 和任务队列持久化到 Supabase，队列通过数据库租约支持独立 Worker 跨进程消费。`AGENT_INLINE_WORKER=true` 仅用于同进程开发。HTTP Run 只接受已登记的 source-document 对象引用，不接受任意本地路径。

Supabase 模式下，完整提取 Proposal 会原子写入规范化结果版本；source document 和 Correction drawing 会从私有 Bucket 下载并校验或重新物化。受控结果工具支持多条件查询、持久 Correction bundle、乐观版本提交和 accepted feedback；Profile candidate、release gate、eval、状态审计和模型 Trace 也会持久化。Stage 1/2/3 本身仍只返回结构化候选，只有完整提取持久步骤或用户明确确认修订后才调用受控提交 RPC。

ABB Profile 仍为 experimental，当前全量 PDF runner 只支持 ZH。已有 ABB 目录虽包含独立样本，但其 Stage 2 prompt 仍使用 ZH 的 XD 起点白名单，不能据此启用 ABB；需先校正规则并由真实 ABB 图纸重新确认 expected JSON。

## 启动

从仓库根目录安装 Agent 包及其运行依赖。首次使用时复制配置模板到 `services/agent/.env`，并填写模型连接参数。`AGENT_MODEL_BASE_URL` 填服务根地址（通常以 `/v1` 结尾），也可以直接填写完整的 Chat Completions 地址到 `AGENT_MODEL_CHAT_COMPLETIONS_URL`。

```powershell
.\.venv\Scripts\python.exe -m pip install -e "services/agent[dev]"
if (-not (Test-Path services\agent\.env)) { Copy-Item services\agent\.env.example services\agent\.env }
```

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

启动 Agent API（当前用于探活、Profile 查询和首页识别；PDF 全链路测试使用下方 CLI）：

```powershell
$env:PYTHONPATH="services/agent/src;."
.\.venv\Scripts\python.exe -m uvicorn agent_service.main:app `
  --host 0.0.0.0 `
  --port 8100
```

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
$env:PYTHONPATH="services/agent/src;."
.\.venv\Scripts\python.exe -m pytest services\agent\tests
```

本地 Supabase 启动并应用 migration 后，可运行真实持久化冒烟。脚本会创建临时用户和项目，验证完成后清理，不调用 VLM：

```powershell
$env:PYTHONPATH="services/agent/src"
$env:AGENT_SUPABASE_URL="http://127.0.0.1:54321"
$env:AGENT_SUPABASE_SERVICE_ROLE_KEY="..."
$env:AGENT_SUPABASE_ANON_KEY="..."
$env:AGENT_SUPABASE_STORAGE_BUCKET="project-assets"
.\.venv\Scripts\python.exe services\agent\scripts\verify_supabase_production_foundation.py
```

该冒烟覆盖私有 Storage、签名 URL、RLS、PDF checksum、页面发布、租约队列、并发事件序号、Artifact、Proposal、Checkpoint 乐观锁与从 1000 开始的并发线号分配。

完整数据库工作流验证不调用 VLM，覆盖提取落库、结果查询、纠错确认、新版本、accepted feedback、Trace、候选、评测、门禁和审计：

```powershell
$env:PYTHONPATH="services/agent/src"
.\.venv\Scripts\python.exe services\agent\scripts\verify_supabase_agent_database_workflows.py
```

若当前环境没有安装可选开发依赖 `pytest`，可用 `unittest` 执行迁移相关回归：

```powershell
$env:PYTHONPATH="services/agent/src;."
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_agent_settings.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_atomic_checkpoint.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_native_vlm_stages.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\integration -p "test_standalone_three_stage_workflow.py"
```

## 三阶段提取

Stage 2/3 会保留 manifest 中的图像 Few-shot，但发送给模型前会将最长边超过 `AGENT_MODEL_FEWSHOT_MAX_IMAGE_SIDE` 的样例图按 2 的幂次缩小，默认最长边不超过 1800 像素。磁盘中的案例图片和待提取原图不变；该配置只控制 Few-shot 请求图像大小。

三个子图供 Extraction Workflow 或本地测试调用，目前尚未暴露为单独 HTTP API：

| 子图 | 输入范围 | 结果 |
| --- | --- | --- |
| `run_page_classification` | 单页图像、已锁定 Profile、已知页面上下文 | Plant Function 与图纸业务页号，保留 PDF 物理页号 |
| `run_page_scan` | 单张当前来源页 | 同页连接和跨页引用占位，不接收目标页图片 |
| `run_cross_page_completion` | 单个端子连接任务、Stage 2 端子元数据、索引确定的一张目标页 | 只输出该端子的终点补全，不含可修改起点的字段 |

ZH 阶段通过 `build_extraction_stage_dispatcher(AgentSettings.from_env())` 注册 `zh_native` adapter。三个子图分别执行图纸归类、当前页扫描和跨页补全；`run_three_stage_extraction` 直接调用公共 `run_document_extraction`，文档 Graph 按阶段调用子 Agent，Profile 策略负责模板算法。Stage 3 按端子连接拆分并串行处理；每次 VLM 请求严格只包含一张目标图，来源页信息通过 Stage 2 元数据传入。同一端子若存在多个候选目标页，会拆成多个独立任务，结果一致时合并，结果冲突时标记 `needs_review`，不会把多张目标页放进一次请求。

模块迁移见 [ADR-0005](../../docs/adr/0005-retire-zh-workflow-runtime.md)。`zh_workflow` 兼容目录已删除，`agent_service.zh_workflow.*` import 不再受支持；所有调用直接使用当前 Graph、domain、基础设施和 Profile 模块。阶段 JSON、checkpoint 文件名与版本、11 列诊断 XLSX 和 Proposal/数据库提交契约保持兼容。严格类型检查使用本包配置：`python -m mypy --config-file services/agent/pyproject.toml services/agent/src/agent_service`；PDF 与 Excel 第三方库的无存根边界在基础设施适配器及 mypy override 中显式处理。

旧相邻页分段和批量提取已删除，包括 segment decider、batch client、batch checkpoint、旧批次合并及关联配置。新运行不再产生旧 `merge_decisions.json` / `extraction_batches.json`，现有三阶段 checkpoint 和结果契约不变。`AGENT_CLASSIFICATION_CONCURRENCY`（旧分段并发别名）、`AGENT_MAX_SEGMENT_PAGES`、`VLM_SEGMENT_CONCURRENCY`、`VLM_MAX_SEGMENT_PAGES` 不再参与配置。旧 import 转发也已删除，原 CLI 命令无需改变。

ZH Stage 3 当前资源位置：

- Prompt：`services/agent/prompts/zh/page_cross_page_completion.md`
- Few-shot 清单：`services/agent/prompts/zh/examples_wiring/002c/manifest.json` 的 `stage3_cases`
- Few-shot 图片：`services/agent/prompts/zh/examples_wiring/002c/images/`
- 任务输入与期望结果：`services/agent/prompts/zh/examples_wiring/002c/stage3/*.task.json`、`*.expected.json`

每个 Stage 3 请求只动态选择一个最相关的图片 Few-shot，即一张目标页样例图片，避免无关样例和来源页占用视觉 patch 预算。

全链路脚本只使用新 Agent 子图、Agent Model Gateway 和已迁入 Agent 包的工作流代码，不从旧 `backend` 导入模块。分类、单页扫描、跨页补全的每一次模型调用都会经过对应的 LangGraph 子图，并在多模态消息中附带 manifest 指定的图像 Few-shot；脚本不写 Supabase 或数据库。

```powershell
$env:PYTHONPATH="services/agent/src;."
.\.venv\Scripts\python.exe services\agent\scripts\run_three_stage_extraction.py `
  "backend\cases\test.pdf" `
  --output-dir "backend\cases\test\agent-run-001" `
  --max-pdf-pages 0
```

产物目录中 `01_page_classification` 存放分页归类 JSON，`02_page_scan` 存放逐页扫描/线单元 JSON，`03_cross_page_completion` 存放跨页任务、补全 JSON 和表格 JSON；标准预览工作簿为 `03_cross_page_completion/table.xlsx`，根目录也会保留一份 `table.xlsx`。若配置了原有导入模板，还会另外生成模板格式的 `wiring-table-import.xlsx`。

桥接测试不调用真实 VLM：

```powershell
$env:PYTHONPATH="services/agent/src;."
.\.venv\Scripts\python.exe -m unittest discover `
  -s services\agent\tests\unit `
  -p "test_three_stage_graph_client.py"
```

未安装 pytest 时仍可做导入和语法检查：

```powershell
$env:PYTHONPATH="services/agent/src;."
.\.venv\Scripts\python.exe -m compileall services/agent/src
```

真实 ZH 全链路需要模型配置，会实际调用模型并产生费用；执行方式见上方脚本命令。不要把固定案例结果与 Fake VLM 测试混为一谈。

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

- `agent_service.domain` 不依赖 FastAPI、数据库 SDK 或模型供应商。
- 新原生子 Agent 通过 Harness 调用模型与工具；`legacy_zh_adapter.py` 与 `legacy_zh_stages.py` 仅保留旧 Agent 调用方的兼容入口，不导入或执行旧 `backend` 实现。
- `LegacyZhExtractionAdapter` 只返回候选结果，不提交生产数据。
- `LegacyZhStageAdapter` 只执行单阶段 VLM 调用并返回候选 Schema，不负责索引、最终校验或生产数据写入。
- ABB 当前保持 `experimental`，不能作为默认生产 Profile。
- Supabase 模式已持久化 Run/Event/Artifact/Proposal/Checkpoint/Trace、源 PDF、页面图片、规范化结果版本、Correction/accepted feedback、候选、评测、门禁审计和租约队列。Profile 沙箱文件仍位于隔离运行目录，实际发布到生产 Profile 的部署执行器尚未实现。
