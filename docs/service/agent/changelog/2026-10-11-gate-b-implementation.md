# Gate B：内部用户链路实现

日期：2026-10-11。状态：接口与 Fake 验收完成；真实模型人工字段准确率未验收。未接 Web/apps/api JWT 或成员代理，不能据此宣称产品上线。

## 行为

业务 raw PDF 上传由服务端验证真实 PDF/加密/页数/大小、登记已有 owner 的项目和 document_files、保存私有 `projects/<uuid>/original.pdf`。owner+Idempotency-Key 固定 UUID，数据库 reservation 固定 checksum，Storage 不覆盖不同内容；网络丢响应重试校验对象。上传不创建用户，源 PDF 无法下载校验时不建立会话引用。部分 reservation 保留以供同 key 补齐，不伪造 completed；长期孤儿清理另行设计。

Supervisor 正常 Graph 接收自然语言，PROCESS_DOCUMENT 先检测物理首页并强制人工确认；UNKNOWN 必须明确类型。确认后创建带 Profile 版本/checksum、确认者、源 checksum、置信度/检测 ID/时间和 base version=0 的 FULL_EXTRACTION protocol 2 run。临时阶段 0 确认不能授权新的业务 PDF；ABB experimental 不可完整提取。重复 OK/turn、同一 import 服务重启后的再确认只返回已有任务，不重新入队，不改原确认审计。

复用 Gate A Worker/阶段提交和从库重建机制。业务任务创建、RUN_CREATED、queue 原子提交，入队失败整体回滚；SQL 持项目锁、限制 owner/source 与 request fingerprint，撤销 anon/authenticated 执行权。只新增一份函数 migration，没有新表，没有改已应用 Gate A migration。

项目树只展开 published 分类 snapshot（分页读取以避免 PostgREST 1000 行截断）。结果按不可变 result version 分页。阶段摘要提供已封存 counts/digest、Profile/模型/final receipt 和阶段持久事件时间跨度；未知费用为 null，不假零。SSE 支持 Last-Event-ID，关闭前排空最后提交事件。服务重启后的 run/tree/results 查询无需短期聊天记忆。

## 文件

- `application/supervisor_conversation.py`、`infrastructure/conversation_memory.py`：业务附件、待确认/已确认来源绑定、固定 run key、去重。
- `domain/models/imports.py`、`domain/models/runs.py`、`domain/schema.py`、`contracts/domain-schema.sha256`：上传/read model/ProfileConfirmation 和固定版本契约。
- `infrastructure/business_imports.py`：不可变源 reservation/Storage 与 owner-scoped 树/分页结果。
- `application/run_read_models.py`：已提交阶段摘要，不从本地状态猜完成。
- `api/routes/imports.py`、`api/routes/runs.py`、`api/routes/supervisor.py`、`main.py`：内部 HTTP/SSE、Supabase 注入和实验 Profile 安全错误。
- `infrastructure/supabase_repositories.py`、`application/extraction_run_executor.py`：原子创建入口与确认/源/actor 校验。
- `supabase/migrations/20261011000000_atomic_business_extraction_creation.sql`：唯一新增 migration，已应用并登记本地库；其他部署需独立应用。
- `prompts/supervisor.md`：明确完整提取/只检测/重复认可语义；不改 ZH/ABB 提取 Prompt/Few-shot。
- `agent_test/1.3stage/run_acceptance.py`、README：stdlib/httpx，HTTP 上传/自然语言/终端确认/SSE/固定版本结果与可选人工 expected 字段差异；不调用工具、数据库、模型或手动推进 stage。
- `tests/integration/test_gate_b_http.py`、`test_gate_b_real_supabase.py`、`tests/assets/gate_b_atomic_creation.sql`：离线 HTTP、真实本地数据库与原子故障回滚测试。

## 验证

- 默认 Agent suite：113 passed、12 skipped（显式真实 DB 测试默认跳过），不调用真实 VLM。
- 本地 Supabase + Fake 模型 HTTP：正常类型识别和 UNKNOWN 后指定 ZH 两场景，验证上传幂等、确认前零入队、固定 Profile、三阶段封存、跨页起点/终点与线号 1000、published 树、终态 SSE、越权拒绝、重启后查询和同 import 不重跑。
- Gate A 追加复验：normal、独立 process_crash 两场景通过（子进程需 `PYTHONPATH=services/agent/src;.`）；其余 Gate A 8 场景本轮未重跑，原门槛记录保留。
- 22 份 migration 链在 UUID 隔离空库/合成旧数据库通过；新增函数验证重复登记、错误 owner/指纹、入队故障无 orphan run，旧合成线表保留。
- strict mypy：156 source files；Ruff、compileall、OpenAPI/domain checksum、客户端 `--help` 和脚本 AST 工具隔离验证通过。Starlette/anyio 既有弃用 warning 不影响结果。

测试清理仅限自身唯一用户/项目与项目前缀对象；未重启既有 API/Worker/Supabase，不调用真实 VLM，不读取/输出密钥。空库验证使用 Auth/Storage prerequisite fixture，不冒充真实 provider 验证；HTTP 场景使用实际本地 Supabase。

## 如何验收真实 PDF

完整命令见 [阶段 1 README](../../../../services/agent/agent_test/1.3stage/README.md)。需要：已有 Auth 用户 UUID；Agent 服务加载新代码且启动 Worker；`AGENT_ACCEPTANCE_ALLOW_REAL_MODEL=true`；终端人工确认与 PDF baseline。目录目前没有阶段 1 PDF，可直接传阶段 0 案例路径，或显式选择其他真实案例。

客户端报告写忽略的 runs 目录，exit 0 只表示 HTTP 过程完毕，不表示字段正确；无 baseline 为 manual_review_required，NEEDS_REVIEW 必须复核。费用 provider 未汇总时 unknown。`--run-id` 只重新监看，不创建新任务；真实准确率/费用基线和外部鉴权部署仍未完成。
