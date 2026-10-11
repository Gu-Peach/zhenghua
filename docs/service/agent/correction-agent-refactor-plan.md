# 纠错 Agent 与 Profile 资源包改造方案

> 状态：代码基础、本地数据库迁移和 ZH bootstrap 已部署；运行服务启用远端包模式和人工验收待完成，详见[部署记录](./changelog/2026-10-11-profile-package-deployment.md)  
> 日期：2026-10-11  
> 范围：Supervisor 纠错编排、Stage 2/3 局部重提取、Improvement 归因、Profile 资源包和 test0 人工验收

## 1. 结论与边界

本次改造采用“结果版本不可变 + 纠错生成新版本 + Profile 资源包不可变版本”的方式。Prompt、Few-shot、expected JSON、规则、Schema 和校验配置作为一个完整资源包上传到私有 Supabase Storage Bucket；数据库只保存资源包的版本和索引元数据，不把大段 Prompt 或图片正文塞进业务结果表。

纠错仍由一个 Supervisor 对用户负责，Stage Agent 和 Improvement Workflow 作为受控内部组件。用户提供的自然语言只用于提取结构化意图，不能直接成为 System Prompt，也不能绕过字段白名单和结果版本校验。

本次明确不做：

- 不新增 Stage 3-only 路径。跨页重新识别统一执行 **Stage 2 → Build Cross-page Tasks → Stage 3**；Stage 2 判断为 `same_page` 时只执行 Stage 2。
- 不新增纠错专用终端脚本或完整案例目录。验收直接复用已经上传并完成三阶段提取的 `test0`，人工在测试结果版本中注入错误，再通过现有 Supervisor HTTP 对话接口输入纠错信息。
- 不让纠错直接覆盖 `wiring_connection_rows` 或旧结果版本。
- 不允许用户确认后自动改生产 Profile；确认只授权创建候选资源包，仍需回归、审核和发布门禁。

## 2. 目标全链路

```text
已有 test0 结果版本
  -> 测试专用版本人工注入错误（保留 baseline）
  -> Supervisor 解析自然语言
  -> CorrectionBatch 确定性拆批
       ├─ direct_patch_batch       -> 字段级 ResultPatchProposal
       ├─ same_page_reextract_batch -> Stage 2
       └─ cross_page_reextract_batch -> Stage 2 -> Build Tasks -> Stage 3
  -> 各批次产物先写 agent_artifacts / trace / event
  -> 统一生成 ResultPatchProposal
  -> 用户确认
  -> Server 以 base_result_version 乐观锁提交新 accepted result_version
  -> Improvement Workflow 异步读取 before/after、图片、阶段产物、Trace、Profile 包
  -> 输出归因与规则建议
       ├─ 幻觉/感知错误：反馈原因，不修改规则
       └─ 规则问题：Supervisor 展示建议并请求确认
              -> ProfilePatchBuilder 沙箱生成候选资源包
              -> 固定回归 + EvaluationJudge + ReleaseGate + 人工审核
              -> 新版本发布为 active（不覆盖旧包）
```

在线纠错的完成条件是新结果版本提交成功；Improvement 失败不能回滚已确认的业务修订，只能以事件和诊断状态标记待处理。

## 3. 混合纠错的结构化批次

### 3.1 `CorrectionItem`

Supervisor 必须把一条用户消息转换为结构化项，字段建议如下：

```json
{
  "item_id": "client-generated-uuid",
  "target": {
    "connection_id": "durable-uuid-or-null",
    "wire_number": "1000",
    "terminal": "X1:3",
    "project_id": "uuid",
    "workspace_id": "uuid",
    "drawing_id": "uuid"
  },
  "mode": "direct_patch | reextract",
  "fields": ["end_terminal"],
  "proposed_values": {"end_terminal": "12"},
  "requested_cross_page": "same_page | cross_page | unknown",
  "user_text": "保留原话用于审计，不作为 Prompt",
  "source": "user"
}
```

稳定 `connection_id` 是执行修改的唯一目标标识；线号、端子和项目/工作区名称只用于检索。检索到多个候选时必须暂停并向用户追问，不得由模型猜选。

### 3.2 `CorrectionBatch`

```json
{
  "batch_id": "uuid",
  "base_result_version_id": "uuid",
  "profile_binding": {
    "profile_key": "zh",
    "profile_version": "1.0.0",
    "package_checksum": "sha256:..."
  },
  "items": ["CorrectionItem..."],
  "batches": {
    "direct_patch": ["item_id..."],
    "stage2": ["item_id..."],
    "stage2_stage3": ["item_id..."]
  },
  "created_at": "RFC3339"
}
```

拆批由确定性代码完成，不由 LLM 决定数据库写入。相同 `(base_result_version_id, item_id, mode)` 幂等；重复请求返回原 proposal/receipt。一个请求可以包含三类 item，执行顺序固定为 direct patch、Stage 2、Stage 2→Stage 3，阶段之间串行且每个阶段完成后才发布 `completed` 事件。

### 3.3 路由规则

| 用户意图 | `is_cross_page` | 执行路径 |
| --- | --- | --- |
| 给出明确答案 | 任意 | 直接生成最小字段 patch，不调用 VLM |
| 要求重新识别 | `same_page` | 目标页 Stage 2 |
| 要求重新识别 | `cross_page` | 目标页 Stage 2，读取新/确认后的跨页任务，再定向 Stage 3 |
| 要求重新识别 | `unknown` | Stage 2 重新判断；仍不足则 `needs_review`，不猜测 |
| 同一条消息含多种情况 | 混合 | 先结构化拆分，按上表分到不同 batch，逐批返回结果 |

跨页路径不允许直接跳到 Stage 3，因为 Stage 2 负责确认起点、方向和跨页任务边界；Stage 3 只能处理 Stage 2 产生的指定任务。

## 4. 阶段性持久化与结果提交

### 4.1 中间结果

- Stage 2 每个目标连接写入不可变 `agent_artifacts` item，包含输入图片引用、冻结的 Profile 绑定、结构化输出、`is_cross_page`、校验结果、模型/耗时/重试和业务结果摘要。
- 跨页任务清单写入 `agent_artifacts` manifest；Stage 3 从该 manifest 和数据库中的固定输入读取，不从内存状态或本地目录推断任务。
- Stage 3 每个任务写入独立 item，保留 before/after、来源图片和引用证据。
- 原始模型响应写入 `agent_traces`；大图片/诊断副本写入私有 Storage，数据库只保存对象引用和 checksum。
- 任何阶段失败保留 attempt/error 历史；只有阶段清单完整且数据库提交成功才允许推进。

### 4.2 纠错结果

所有路径都先生成 `ResultPatchProposal`，包含：`proposal_id`、`base_result_version_id`、目标 connection IDs、字段级 `before/after`、证据引用、阶段 artifact IDs、profile package checksum、确定性校验、`unchanged_assertions` 和幂等键。

用户确认后由受控 `commit_result_patch` RPC 创建新的 `result_version`，并在事务中写入规范化的 `wiring_units`、`wiring_connections`、`connection_evidence`。原版本保持可读，`wiring_connection_rows` 只展示当前发布版本。确认前任何 Agent 都不能写生产结果。

## 5. Profile 资源包设计

### 5.1 Bucket 目录

新增私有 Bucket：`agent-profile-assets`。对象内容不可变，禁止覆盖同一版本路径：

```text
agent-profile-assets/
  zh/
    1.0.0/
      manifest.json
      prompts/
        profile_router.md
        page_classification.md
        page_scan_index.md
        page_cross_page_completion.md
        improvement_diagnosis.md
        profile_patch_builder.md
      fewshot/
        page_classification/...
        stage2/...
        stage3/...
      expected/
        .../*.json
      rules.json
      schema.json
      validation.json
      CHANGELOG.md
```

`manifest.json` 必须列出每个文件的相对路径、类型、sha256、媒体类型、适用 stage、expected schema 版本和资源包总 checksum。图片 Few-shot 与 expected JSON 必须成对登记；manifest 中的路径必须在上传后逐项校验。

### 5.2 数据库元数据

新增 migration（实施阶段再创建）`profile_resource_packages`，建议字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 资源包 UUID |
| `profile_key` / `profile_version` | `zh@1.0.0` 等不可变绑定 |
| `status` | `draft`、`candidate`、`active`、`retired` |
| `storage_bucket` / `storage_prefix` / `manifest_path` | 私有 Bucket 对象位置 |
| `package_checksum` / `manifest_checksum` | 完整性和复现校验 |
| `base_package_id` | 候选从哪个 active 包派生 |
| `created_by` / `approved_by` / `published_at` | 审计与发布信息 |
| `created_at` / `updated_at` | 管理时间 |

如果最终决定复用 `profile_candidates`，必须新增明确的资源包引用和生命周期字段，区分“候选诊断记录”和“可加载生产包”；不能只把整个包塞进 `profile_candidates.payload`。本方案默认使用独立元数据表，避免生产 Profile 与候选混义。

### 5.3 加载边界

提取 Worker、Correction Workflow 和 Improvement Workflow 都使用同一个 `ProfilePackageRepository`：按 frozen `profile_key/version/checksum` 下载 manifest，逐项校验后缓存到本地运行目录。缓存丢失可以重建；checksum 不一致、包状态不是允许状态或 manifest 缺文件时，任务失败且不推进阶段。

前端只能通过业务 API 获取包元数据、Prompt 文本和短期签名 URL；不能暴露 Supabase service-role key。展示接口默认脱敏内部密钥和模型凭据，但保留版本、checksum、文件路径和变更说明。

## 6. Improvement 归因输入与输出

### 6.1 必须读取的证据

`ImprovementDiagnoserAgent` 不再只接收 feedback ID。Context Builder 按 `feedback_id + result_version_id + profile_package_id` 组装：

- 原始错误值、用户确认值、字段和 connection ID；
- `feedback_origin`（生产反馈或 `manual_injected_test_error`）；
- 原图/目标图纸的私有 Storage 引用、物理页和业务页码；
- Stage 2/Stage 3 committed artifact、deterministic validation 和事件；
- 原始模型响应、trace、模型名、耗时和重试；
- 当次使用的 Profile package 版本/checksum、Prompt、Few-shot 图片和 expected JSON；
- 保护性/未修改字段断言和结果版本差异。

### 6.2 输出契约

诊断输出必须结构化：

```json
{
  "category": "MODEL_PERCEPTION_ERROR | PROMPT_RULE_GAP | DETERMINISTIC_RULE_ERROR | CROSS_PAGE_RESOLUTION_ERROR | SOURCE_INSUFFICIENT",
  "confidence": 0.0,
  "evidence": ["artifact/...", "profile/prompts/page_scan_index.md#..."],
  "affected_stage": "stage2",
  "affected_fields": ["end_terminal"],
  "profile_path": "prompts/page_scan_index.md",
  "problem_excerpt": "...",
  "recommended_change": "...",
  "regression_cases": ["..."],
  "feedback_origin": "manual_injected_test_error"
}
```

人工注入的 test0 错误只能证明纠错路由、持久化和确认闭环，不能单独证明原始模型产生了幻觉或 Profile 有规则缺陷。归因必须携带 `feedback_origin`，诊断 UI 也要显示该限制。

## 7. ProfilePatchBuilder 与发布边界

ProfilePatchBuilder 只能在沙箱复制完整资源包并生成候选 diff：

- 允许 `add/replace/remove`：Prompt、Few-shot、expected JSON、rules/schema/manifest、CHANGELOG；
- 代码、通用解析器和校验器只能输出 `suggest_code_change`，不得自动编辑生产代码；
- 候选包必须通过 manifest、checksum、Schema、正例/负例/跨页回归；
- 用户确认“创建规则候选”后才上传 `candidate` 包；这不等于批准发布；
- EvaluationJudge、ReleaseGate、人工 reviewer、canary 和 rollback 保持现有门禁；历史 run 继续绑定旧包版本。

## 8. 代码、迁移和文档修改清单

以下为实施顺序和预期文件，当前仅方案，不执行：

### Phase A：契约与批次（先做）

1. `services/agent/src/agent_service/domain/models/correction.py`：新增 `CorrectionItem`、`CorrectionBatch`、批次状态和幂等键模型。
2. `services/agent/src/agent_service/tools/correction_router.py`：把自然语言解析结果转为结构化 item，确定性拆分 direct/Stage2/Stage2→Stage3；多目标自动分批，歧义才追问。
3. `services/agent/src/agent_service/application/correction_workflow.py`：按批次串行调度、阶段屏障、proposal 合并和事件反馈。
4. `services/agent/src/agent_service/agents/supervisor.py`、`application/supervisor_conversation.py`：持久化待确认 batch，支持混合输入和恢复，不依赖单一 `target_hint`。
5. `services/agent/src/agent_service/api/schemas/supervisor.py`：同步请求/事件/确认 DTO。

### Phase B：资源包与运行时加载

1. `services/agent/src/agent_service/profiles/package.py`、`profiles/package_repository.py`：manifest、checksum、签名 URL、缓存和版本校验。
2. `services/agent/src/agent_service/profiles/registry.py`：本地开发保留兼容读取；生产/纠错/Improvement 优先按 frozen package 加载。
3. `services/agent/src/agent_service/infrastructure/supabase_profile_packages.py`：Bucket 上传、下载、元数据查询和候选包引用。
4. `services/agent/src/agent_service/application/improvement_run_executor.py`、`agents/improvement_diagnoser.py`、`agents/profile_patch_builder.py`：注入完整 Profile 包和证据 bundle。
5. `services/agent/src/agent_service/harness/profile_sandbox.py`：从完整包创建沙箱，不能只复制当前 Profile 目录。
6. 新 migration：`supabase/migrations/<timestamp>_create_profile_resource_packages.sql`，包括唯一约束、状态约束、RLS、索引和项目/用户审计路径；另建私有 Bucket 配置/种子步骤。

### Phase C：结果与数据库适配

1. `services/agent/src/agent_service/infrastructure/supabase_result_data.py`：补齐真实 artifact/trace IDs，禁止 `run_id:correction` 等占位引用；proposal 合并保持 base version 校验。
2. `services/agent/src/agent_service/infrastructure/correction_data.py`、`tools/result_data.py`：支持批量 bundle、混合 proposal 和稳定 connection ID。
3. `services/agent/src/agent_service/infrastructure/supabase_improvement.py`：持久化诊断证据、候选包 ID/checksum 和发布审计。
4. `services/agent/src/agent_service/graphs/correction`、`graphs/improvement`：接入 artifact/trace/profile package 读取，不允许绕过 repository。

### Phase D：验收与文档

1. 只更新 `services/agent/agent_test/2.纠错agent/test.md` 记录手工验收，不创建 `run_acceptance.py`。
2. 更新 `docs/service/agent/README.md`、`supervisor-agent-orchestration-v2.md`、`feedback-and-improvement.md` 的资源包和混合批次描述。
3. 更新 `docs/TODO.md`、`docs/roadmap.md` 和 `docs/changelog/README.md`；新增本方案对应 ADR-0009。

## 9. test0 人工验收方案

### 9.1 前置准备

1. 使用已完成提取的 test0 项目 `3d66b325-bfe1-5227-9d95-0f22260fd0b0` 及其结果版本作为 baseline。
2. 创建测试专用结果版本或隔离测试项目；禁止直接修改 baseline 和 `wiring_connection_rows` 当前发布版本。
3. 人工注入若干错误字段，所有注错记录标记 `origin=manual_injected_test_error`，保留 before/after 和注错人/时间。
4. 确保 Agent 服务使用 frozen Profile package，并记录 run ID、result version ID 和 package checksum。

### 9.2 手工输入案例

通过已有 `/v1/supervisor/turns` 或 `/v1/supervisor/turns/stream`，在同一会话中依次输入：

| 案例 | 输入意图 | 期望路径 |
| --- | --- | --- |
| A | 指定线号/端子并给出正确字段值 | direct patch，返回 before/after，等待确认 |
| B | 指定同页错误，要求重新识别 | Stage 2，生成 proposal |
| C | 指定跨页错误，要求重新识别 | Stage 2 → Stage 3，生成 proposal |
| D | 一句话同时包含 A/B/C 多个目标 | 拆成三个 batch，串行反馈，不混写字段 |
| E | 同类型多个目标 | 一个批次多个 item，逐项结果和稳定 ID |
| F | 规则建议被用户拒绝 | 保留诊断，不创建 candidate 包 |
| G | 规则建议被用户确认 | 创建 candidate sandbox/package，跑回归，仍不自动 active |

### 9.3 验收检查

- Supervisor 事件明确显示“正在执行 Stage 2/Stage 3”和完成状态；
- 每个 Stage 2/3 item、manifest、trace 在 `agent_artifacts`/`agent_traces` 可按 run/stage/item 查到；
- proposal 的 before/after、证据、Profile checksum 和 base version 正确；
- 用户未确认前无新 accepted result version；确认后只创建新版本，旧版本不变；
- `wiring_connection_rows` 仅切换到已发布的新版本；
- Improvement 读取完整图片、阶段产物、Trace 和资源包，输出归因及建议；
- manual injected 错误不会被报告为确定的模型幻觉；
- 规则建议拒绝不会创建候选，确认只创建候选，不直接修改 active 包；
- 重复 HTTP 请求返回相同 proposal/receipt；服务重启后能从持久 batch/checkpoint 恢复；
- 权限、歧义目标、过期 base version、checksum 不一致和 Stage 失败均返回稳定错误，不写越权数据。

## 10. 实施门槛与回滚

先完成 Phase A 的离线契约和 Fake VLM 测试，再新增 migration 和 Bucket 元数据，最后接入真实 Supabase/HTTP。每一步都保留本地 Profile Registry 和现有提取链路作为兼容回退；新资源包加载失败时不能静默回退到未绑定的 active 文件，必须显式记录兼容模式。数据库迁移只新增结构，不修改已应用历史迁移；回滚通过关闭新入口或将 active 指针切回旧 package，不删除历史 artifact、result version 或资源包。

