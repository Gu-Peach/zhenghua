# Changelog

This directory records cross-module architecture and product behavior changes.
Detailed application work is archived under `docs/apps/`; service work is
archived under `docs/service/`.

详细变更见 [CHANGELOG.md](./CHANGELOG.md)。

## 2026-10-13

- 项目切换改为保留框架、局部加载，目录不随选择重拉；Server 项目列表按创建时间/ID 固定排序，更新/选择不置顶。17 项浏览器回归、29 项 Server 默认测试及 Web 检查通过，见 [Web 记录](../apps/web/changelog/2026-10-13-stable-project-switch.md) 和 [Server 记录](../service/server/changelog/2026-10-13-stable-project-order.md)。

- 左侧项目目录点击名称/文件夹直接切换项目，箭头控制当前项目折叠，移除二次“打开项目”入口。17 项浏览器夹具及 Web 检查通过，见 [记录](../apps/web/changelog/2026-10-13-project-folder-navigation.md)。

- 导航和搜索按容器水平居中，线表记录改为原位编辑，复用既有 PATCH/版本锁/幂等和审计，取消编辑弹窗；16 项浏览器夹具、Web typecheck/lint/build 与桌面/窄屏截图检查通过。见 [Web 记录](../apps/web/changelog/2026-10-13-centered-inline-edit.md)。

- 工作台精简：新增端子改为最右侧加号，移除全部工作区按钮和重复项目概览；导航显示当前项目名，左侧项目可折叠并移除 PDF 中间节点；聊天去掉独立当前阶段卡片。13 项浏览器回归、Web typecheck/lint/build 和截图检查通过，见 [Web 记录](../apps/web/changelog/2026-10-13-workbench-cleanup.md)。

- 图纸库改为项目→工作区→图片原地展开和预览，替代平铺点击切换线表。聊天从固定右栏改为右下角按钮控制的悬浮窗口，保留草稿、任务订阅及人工确认；13 项浏览器夹具、前端 typecheck/lint/build 和桌面/窄屏截图检查通过。见 [Web 记录](../apps/web/changelog/2026-10-13-directory-floating-chat.md)。

## 2026-10-12

- 规则库取消手工包草稿门槛：所有登录用户共享读取，写入后直接可用；同 key 新任务选择最新 active 版本，历史 checksum 保留，Improvement 隔离候选及其精确回滚仍受审核范围保护。三个 additive migration 已应用并通过非创建者 RLS、空库/旧数据重放。ABB 1.1.2 已接入独立三阶段 adapter/policy、上传并读回校验，当前可执行但真实模型字段准确率仍待验收。见 [ADR-0012](../adr/0012-shared-ready-rule-library.md)、[Server 记录](../service/server/changelog/2026-10-12-shared-rule-library.md) 和 [Agent 记录](../service/agent/changelog/2026-10-12-abb-ready-profile.md)。

- 候选目标评测的 Stage 2 上下文补齐明确起点定位，保留正确终点隔离和严格起点匹配；不改 Profile/数据库/发布门禁。32 项相关离线回归通过，真实模型未运行，旧冻结评测不会因重载或 resume 自动重测，见 [Agent 修复记录](../service/agent/changelog/2026-10-12-evaluation-source-locator.md)。

- 图纸库只展示当前项目的图纸目录，不展示旧的项目文件夹列表或工作区分组；线表左侧导航仍保留工作区层级。该条最初实现了规则状态显示，后续已由同日共享规则库决策取代。
  - 收尾增加空目录/跨工作区定位回归，最终 11 项浏览器夹具与 Web typecheck/lint/build 通过，截图已检查。ABB 创建者已只读核对，用户当前账号可见性尚待确认，见 [Web 记录](../apps/web/changelog/2026-10-12-resource-library.md)。

- 按用户要求将 ABB 样例精简为三个阶段各一例、图片 1/1/2 张；abb@1.1.1 草稿上传私有 Bucket，18 文件读回核验通过，不覆盖旧不可变包或生产绑定。见 [Agent 精简记录](../service/agent/changelog/2026-10-12-abb-resource-compact.md)。

- ABB 1.1.0 三阶段资源改为独立 Prompt/图片/manifest/expected/task 格式，上传私有 agent-profile-assets 草稿并读回验证 45 文件；不替换生产包或项目绑定。独立确定性策略和真实模型验收尚未完成，见 [Agent 资源实施记录](../service/agent/changelog/2026-10-12-abb-resource-draft.md)。

- 规则库支持基于已发布模板新建规则包并自动注册给 Agent；创建者可确认删除/停用，新任务不再选择，历史项目仍按冻结 checksum 读取资源。复用现有私有 Bucket、包元数据和发布 RPC，无 migration；新增 JWT 业务接口、Web 表单/确认和跨进程 Registry 刷新。离线验证与环境限制见 [Server 实施记录](../service/server/changelog/2026-10-12-rule-package-lifecycle.md)。

- 独立结果审校对账遇到 `matched` 但缺少 `connection_id` 时改为保存为 `needs_review` 并继续后续页面，避免单个模型结构错误中断整批；该行不计为已确认匹配。离线回归覆盖，未调用真实模型。

- 规则候选新增服务端 PROFILE_EVALUATION：固定三阶段/负例及 accepted-feedback 目标同图比较，持久评测 receipt，人工审核和发布分别确认；不可变 Bucket 包通过既有 RPC 发布，旧项目 Profile 冻结保留。公开审核契约要求 evaluation_run_id，旧外部报告不作为发布证据。49 项离线回归通过，未调用真实模型或发布候选，见 [Agent 记录](../service/agent/changelog/2026-10-12-candidate-release.md)。

- 用户授权后的真实模型 Web→Server→现有 Agent 联调：PDF 上传/检测/人工确认后三阶段成功落库（5 页/13 连接，约 226 秒），真实 Bucket 三阶段资源面板和图纸索引通过。浏览器退出，纠错/确认/归因仍待验收；新增同项目续跑避免重复提取。自动审批服务自身模型权限 403 使续跑命令未执行，临时数据保留，不改 Schema/Agent 核心/test0。见 [联调状态](../service/server/changelog/2026-10-12-live-agent-acceptance.md)。

- 按用户授权补齐端子新增/删除：Server 既有表原子事务、稳定 ID/线号/代次、完整证据审计与版本/幂等保护，Web 入口与 OpenAPI 同步。24 项默认 API/5 项浏览器夹具通过；真实一次性 Auth/数据库/Storage/API/浏览器增改删、双图及越权/过期/冲突/重放/审计失败回滚通过并清理，不改 test0/Schema/Agent 核心。完整上传/纠错验收未完成：共享队列 Fake 提取测试在 Worker claim 失败，有用户活跃消费者，未停服务。详见 [Server 最新记录](../service/server/changelog/2026-10-12-real-workbench.md) 与 [ADR-0011](../adr/0011-manual-connection-insert-delete.md)。

- 修复 Gateway 误截补丁 JSON 字符串内嵌 Markdown 示例：先解析完整 JSON、仅剥离真正外层 fence。实际失败输出只读重放及31项相关离线测试通过；严格校验/发布门禁不变，未调用模型或写数据库。见 [Agent 记录](../service/agent/changelog/2026-10-12-embedded-fence-json-fix.md)。

- 修复 ProfilePatchBuilder 的模型输出契约：只读 Trace 确认 invalid_json，动态注入实际 JSON Schema、完整文件字符串/转义/包相对路径要求；严格校验及发布门禁不变。11 项相关离线回归通过；未重复修订数据或调用真实模型，详见 [Agent 修复记录](../service/agent/changelog/2026-10-12-profile-patch-output-contract.md)。

- 独立结果审校支持跨页引用页码 null/空白：保留原始引用并标记待复核，继续后续页面；修复已访问页循环漏检。11 项离线回归通过，未调用真实模型，未改生产 Agent/数据库。脚本修改生成新验证快照，旧报告保留但缓存不复用，见 [审校说明](../test/agent-run-001/VALIDATION_README.md)。

- 完成性核对补齐规则包逐阶段 manifest 样例展示、纠错确认/刷新/归因说明与候选状态、内部 Agent 鉴权错误与上传请求头边界。21 项 Server、5 项浏览器夹具及真实资源包只读验证通过；完整真实验收与端子增删范围仍需用户选择，目标未完成。见 [完成性记录](../service/server/workbench-completion-audit.md)。

- 真实工作台收尾修复：首次自动检测在 StrictMode 下被取消、最终确认消息遗漏、阶段卡片重复、错误待确认状态；补共享单元字段编辑、续传/重连、图片签名刷新、Auth 并发续期/过期退出与完整上传响应匹配。18 项 Server、4 项浏览器夹具回归通过；真实登录/写入/模型联调及端子增删范围仍待确认，不改数据库或 Agent 核心。

- 开始真实 Web/Server 接入：新增 apps/api 与 services/server，Supabase Auth/项目权限、真实树/线表分页与手动修订、私有图纸/规则资源、Agent HTTP/SSE 安全代理；Web 切换真实接口、组首页码/线号、表格下方跨页预览、规则样例面板与可缩放布局。无 migration/Agent 核心改动。Fake API/Web 与只读真实库验证已执行，写入和真实模型全链路验收仍未完成，见 [实施进度](../service/server/changelog/2026-10-12-real-workbench.md)。

## 2026-10-11

- Fixed Improvement diagnosis requests to include the runtime Diagnosis JSON Schema and exact field/enum constraints, retaining strict validation and compatible provider settings. Twenty-four focused offline checks passed; existing committed corrections were preserved. Reload and resume only the failed diagnosis run for live verification. See [Agent record](../service/agent/changelog/2026-10-11-improvement-diagnosis-schema-fix.md).
- Fixed scoped-correction source matching so location and device identifiers are not compared as equivalent fields; missing, ambiguous or duplicate targets now fail explicitly instead of silently omitting fixes. Added safe Worker failure-location logs. Thirty-three focused offline checks and cached Stage-2 read-only replay passed; no database writes, real-model call or service restart. See [Agent record](../service/agent/changelog/2026-10-11-scoped-correction-source-matching-fix.md).
- Prepared three user-authorized test0 terminal-error injections for direct-answer, same-page and cross-page acceptance, checking source/target PDF evidence first. Backups, expected fields and natural-language input are stored in ignored local run assets; only the three latest connections were changed and revision counters advanced. No Profile mutation, model execution or service restart.
- Added the first HTTP-only mixed-correction terminal acceptance client with human confirmation, SSE/stage outputs, stable-row checks, and honest no-rule-issue/inconclusive/unexpected-candidate-rejection outcomes. Added owner-scoped structured model-output views without hidden reasoning or prompts. Offline mock checks passed; no real model, database mutation or service restart. The second rule-issue script is intentionally deferred. See [record](../service/agent/changelog/2026-10-11-correction-terminal-acceptance.md).
- Changed confirmed scoped corrections to in-place updates per user request (ADR-0010): stable connection/unit/evidence IDs and wire numbers, result revision and record-version checks, feedback audit, and idempotent receipts. Full extraction still creates generations. Applied additive local migration `20261011020000`; focused offline and synthetic rollback checks passed. Existing test0 values/history were preserved; services were not restarted. See [record](../service/agent/changelog/2026-10-11-in-place-corrections.md).
- Fixed post-confirmation Improvement startup: use the correction run's real PDF reference instead of its feedback ID, preserve the accepted Profile, and return committed-result details even when asynchronous diagnosis startup fails. Read-only inspection confirmed case-A result version 2 was already accepted; no correction was rolled back/recommitted. Five focused tests and strict typing passed. See [Agent record](../service/agent/changelog/2026-10-11-confirmation-improvement-source-fix.md).
- Fixed case-A Supervisor schema validation: accept integer page/wire search terms as text, support directional terminal selectors in both result repositories, and inject the actual output JSON Schema. Failed structured responses retain private traces while HTTP exposes only schema/field error types. Twenty-three focused offline tests and strict typing passed; an isolated real-model decision matched one connection without dispatching or writing results. See [Agent record](../service/agent/changelog/2026-10-11-supervisor-correction-schema-fix.md).
- Applied and registered the additive Profile-package migration on local `zhenghua_test`, published the unchanged ZH bootstrap matching test0's frozen checksum, verified all 29 resource files/private Storage/anonymous isolation, and preserved wiring-data digests. Fixed empty-success responses from void PostgREST RPCs (six focused tests passed). No Agent restart, runtime-mode switch, or real-model call. See [deployment record](../service/agent/changelog/2026-10-11-profile-package-deployment.md).
- Implemented correction mixed-batch orchestration, one-proposal version commits, durable scoped stage artifacts, enriched diagnosis evidence, self-contained immutable Profile package adapters and gated publish/rollback hooks. Twenty-six focused offline tests and strict typing/lint passed. Local Supabase is not running, so migration/package deployment and live acceptance remain pending; non-extraction RUNNING takeover and conversation durability are not implemented. See [implementation/deployment record](../service/agent/changelog/2026-10-11-correction-packages-implementation.md).
- Implemented Gate B internal business PDF import, human-confirmed frozen Profile/run creation, atomic run/event/queue registration, published project-tree and versioned result read models, resumable SSE, and a tools-free terminal HTTP client. Fake HTTP and local Supabase/Fake model verification passed; real-model field accuracy and browser JWT/Web integration remain pending. See [Agent record](../service/agent/changelog/2026-10-11-gate-b-implementation.md).
- Documented the proposed Correction Agent resource-package and mixed-batch design. Cross-page re-extraction remains Stage 2 -> Stage 3; correction acceptance reuses test0 with manually injected errors through the existing Supervisor HTTP interface, with no new terminal script. No code, migration, Bucket package, or production Profile was changed. See [plan](../service/agent/correction-agent-refactor-plan.md) and [ADR-0009](../adr/0009-profile-resource-package-storage-and-correction-batches.md).

## 2026-10-10

- Completed Gate A mechanism acceptance: protocol-2 durable stage snapshots/read barriers, RUNNING takeover/fencing, immutable classification publication and finalization receipts. Ten real-Supabase/Fake-VLM scenarios passed in batches, including isolated worker-process recovery; 21 ordered migrations passed empty/legacy synthetic verification. Legacy runs remain compatible; Gate B user-flow integration and real-VLM evaluation remain pending. See [implementation record](../service/agent/changelog/2026-10-10-gate-a-implementation.md).
- Restored the local Git metadata from the retained `.git-new` repository, preserving the existing history and `Gu-Peach/zhenghua` origin. Excluded local extraction outputs, caches and environment secrets; enabled tracking of versioned Agent prompt images. This repository maintenance does not implement the proposed stage-persistence changes.

- Documented the proposed durable extraction-stage boundary: typed per-item database outputs, immutable manifests, atomic commit/event barriers and database-backed inputs for the next stage. See [plan](../service/agent/stage-persistence-refactor-plan.md); no runtime or database change has been applied for this proposal.
- Refined that proposal to V1.1 after consistency review: leased RUNNING takeover with fenced mutations, authoritative item sets, recoverable finalization receipts, atomic classification-tree publication, explicit digest/conflict rules and separate mechanism/user-flow acceptance gates. Documentation only; runtime and migrations remain pending.
- Fixed the OpenAI-compatible model request boundary so structured Supervisor context is serialized as JSON string content; multimodal message arrays remain unchanged. This resolves the stage-zero 400 error from providers that reject object-valued `message.content`; the Agent service must reload this code before retrying the live test.
- Made provider-side `response_format` opt-in. Local structured output validation remains enabled through Pydantic, while endpoints that require a server startup flag are no longer sent `response_format` unless `ModelRequest.json_mode=true`.
- Added a detection-only Supervisor conversation flow with terminal-driven HTTP acceptance, streamed planning/dispatch messages and explicit Profile confirmation. The API now remembers recent turns, attachments and pending decisions in bounded per-user, per-conversation process memory; task checkpoints remain separate, and restart/shared-instance or long-term conversation persistence is not implemented.
- Removed the remaining `agent_service.zh_workflow` import-compatibility package and switched its tests to current modules. Legacy Python import paths are no longer supported; existing Agent HTTP/Worker and CLI entry points retain their current behavior.
- Removed the retired adjacent-page segmentation and batch-extraction implementation, its dedicated checkpoint/planner/configuration and compatibility exports. Production Agent/CLI continue to call the new document Graph directly; retained legacy imports forward current capabilities to that same implementation.
- Retired the production dependency on `zh_workflow`: shared document Graph, domain stage models, PDF/checkpoint/export infrastructure and injected ZH Profile policies now own the implementation. Legacy imports forward to those modules; stage artifacts, result proposals and database contracts retain their shapes. See [Agent migration record](../service/agent/changelog/2026-10-10-document-workflow-migration.md).

## 2026-10-08

- Established the project, workspace, drawing and wiring-result domain model.
- Added the gradual monorepo migration plan while preserving legacy frontend
  and backend implementations.
- Selected React + Vite + TypeScript for the new `apps/web` application.
- Standardized the frontend source structure around API, component, hook,
  layout, router, store and view ownership.
- Added module-specific documentation archive rules to `AGENTS.md`.
- Established the Supervisor-led orchestration boundary and deterministic correction routing; runtime Graph integration remains pending the M4 gate.
- Added isolated Page Classifier, Page Scanner and Cross-page Resolver subgraphs backed by the existing ZH stage adapter.

## 2026-10-09

- Completed the Agent-to-Supabase data path: full extraction now creates normalized draft/review result versions atomically; confirmed corrections create accepted versions with optimistic checks and accepted-feedback audit. Correction bundles, model traces, Profile candidates, release gates, evaluations and lifecycle audit are durable in Supabase. Stage agents still cannot issue arbitrary writes, and Profile activation remains human-gated.
- Applied the normalized domain and Agent runtime migrations to the local Supabase stack, added the private `project-assets` hierarchy, persistent run/event/artifact/proposal/checkpoint repositories, a lease-based queue, source-PDF checksum verification, classified page publication, and signed-URL access. The legacy table and public bucket remain untouched; hosted Supabase deployment and Server-owned result transactions remain pending.
- Updated the `apps/web` Mock Supervisor workflow to start only after explicit user activation; PDF workspaces and split drawings appear after Stage 1 completes, while thought and Agent status events stream in stage order.
- Added the Agent Run/Worker/SSE control plane, Supervisor and scoped Correction workflows, plus a sandboxed evaluation and human-gated Profile candidate lifecycle. Production persistence and Server/Web integration remain explicit follow-up work.
- Added a normalized wiring schema migration: project/workspace/drawing/result-version ownership, terminal-strip units with database-assigned wire numbers, queryable connection columns, evidence, RLS and a flattened search view. The legacy JSONB table remains unchanged and remote application is still pending.
- Completed the offline Supervisor orchestration V2: internal first-page Profile Detection, controlled multi-key result lookup and versioned correction, three-state cross-page routing, accepted-feedback diagnosis, explicit Profile candidate authorization, and sanitized diagnosis/candidate events. Production Supabase/Server adapters remain pending.
