# 用户反馈、局部重提取与自完善

> 状态：Draft  
> 核心原则：在线修数据，离线改规则；两个闭环必须隔离。

## 1. 两条闭环

### 在线 Correction Loop

目标是尽快修复当前项目结果：

```text
用户反馈
-> 定位业务对象和来源证据
-> 判断受影响阶段和最小范围
-> 局部重提取
-> 新旧结果 diff
-> 人工确认
-> Server 创建新结果版本
```

它不修改生产 Profile，只在本项目生成结果补丁。

### 离线 Improvement Loop

目标是改善后续项目：

```text
已接受反馈集合
-> 问题聚类与根因分析
-> 候选 Profile 变更
-> 沙箱回归评测
-> 人工审核
-> canary
-> 发布或回滚
```

它不直接修改当前项目结果，也不能由单条反馈触发生产发布。

## 2. Feedback 数据

用户提交反馈时应尽可能结构化：

```json
{
  "feedback_id": "feedback-uuid",
  "project_id": "project-uuid",
  "result_version": 3,
  "target": {
    "type": "CONNECTION",
    "id": "connection-uuid",
    "field": "end_terminal"
  },
  "issue_type": "INCORRECT_VALUE",
  "current_value": "FC103:3",
  "suggested_value": "FC103:2",
  "user_reason": "图纸 003.C/20 的放线标记连接到 2 号端子",
  "attachments": [],
  "submitted_by": "user-uuid"
}
```

Target 支持：

```text
CONNECTION_FIELD   某条线表的单个字段
CONNECTION         某条完整连接
DRAWING            某张图纸的全部连接
WORKSPACE          某个工作区线表
PROJECT            全项目，仅管理员可用
PROFILE_RULE       规则建议，不直接重跑生产数据
```

用户反馈文本是不可信数据，只作为 `user_reason` 传入；不得拼接到 system prompt，也不得允许其改变工具权限。

## 3. 离线问题归因

问题归因不再阻塞在线修订。在线 Correction Workflow 先根据持久化索引和固定矩阵修复当前结果；只有修订被用户接受后，`ImprovementDiagnoserAgent` 才读取原图、阶段输出、Profile/模型版本和 diff，输出固定 Schema：

```json
{
  "category": "CROSS_PAGE_RESOLUTION_ERROR",
  "confidence": 0.91,
  "affected_stage": ["STAGE_2", "STAGE_3"],
  "affected_scope": {
    "type": "CONNECTION",
    "ids": ["connection-uuid"]
  },
  "evidence_ids": ["evidence-1", "trace-22"],
  "explanation": "Stage 2 提取了正确引用，但目标页列号解析错误",
  "recommended_action": "REBUILD_CROSS_PAGE_TASK_AND_RERUN_STAGE_3",
  "profile_candidate_required": true,
  "needs_human_input": false
}
```

根因分类：

| 分类 | 判断依据 | 典型动作 |
| --- | --- | --- |
| `PROFILE_ROUTING_ERROR` | 图纸标准选择错误 | 重新识别 Profile，完整重跑 |
| `PAGE_CLASSIFICATION_ERROR` | 工作区或业务页号错误 | 重跑 Stage 1 及受影响后续阶段 |
| `MODEL_PERCEPTION_ERROR` | 图上清晰可见但模型读错 | 带错误说明局部重跑，进入模型/样本统计 |
| `PROMPT_RULE_GAP` | 多个相似案例按同一方式错误 | 候选 Prompt/Few-shot 变更 |
| `CROSS_PAGE_RESOLUTION_ERROR` | 引用正确但目标页/列定位错误 | 修复索引或 resolver，重建 Stage 3 task |
| `DETERMINISTIC_RULE_ERROR` | 白名单、方向、归一化或去重错误 | 修改 validator/normalizer 候选 |
| `SCHEMA_MAPPING_ERROR` | Agent 值正确但表字段映射错误 | 修复 mapper，不重调 VLM |
| `SOURCE_INSUFFICIENT` | 图纸没有所需信息 | 标记外部资料需要，不重试幻觉 |
| `USER_EXPECTATION_MISMATCH` | 建议与图纸证据冲突 | 请求用户补充依据 |
| `TRANSIENT_MODEL_ERROR` | 超时、截断、非法 JSON | 自动重试原阶段 |

诊断不能只看新旧最终 JSON，必须读取原图、阶段输出、Prompt/Profile 版本和工具轨迹。

## 4. 最小重跑矩阵

| 反馈范围/问题 | 最小执行范围 |
| --- | --- |
| 同页端子、描述、电流读错 | 当前 Drawing 的 Stage 2 + 校验 |
| 跨页终点错误 | 来源连接 Stage 2 引用复核 + 重建 task + 单连接 Stage 3 |
| 起点漏提 | 当前 Drawing Stage 2；新增连接再执行相关 Stage 3 |
| 重复记录、排序、字段格式 | 仅确定性 normalize/deduplicate/mapper |
| 图纸业务页号或工作区错误 | 受影响页面 Stage 1 + 工作区 Stage 2/3 |
| 整个工作区规则不适用 | 工作区 Stage 2/3，使用候选配置 dry-run |
| Profile 识别错误 | Profile Detection + 全项目提取 |
| 图纸无信息 | 不重跑，标记 `SOURCE_INSUFFICIENT` |

默认禁止“有问题就整本 PDF 重跑”。确定性 Correction Router 必须记录为什么选择该范围，并估算页面数、模型调用数和受影响记录数。

## 5. CorrectionContext

局部重提取时，错误理由不能直接追加为自由 Prompt。Harness 构造结构化上下文：

```json
{
  "feedback": {
    "field": "end_terminal",
    "observed_problem": "用户认为终点端子识别错误",
    "suggested_value": "FC103:2"
  },
  "constraints": {
    "preserve_start": true,
    "allowed_target_drawings": ["drawing-b"],
    "allowed_connection_ids": ["connection-uuid"],
    "do_not_modify_unrelated_rows": true
  },
  "evidence": {
    "source_drawing_id": "drawing-a",
    "target_drawing_ids": ["drawing-b"],
    "reference_raw": "003.C+.../20.2"
  },
  "instruction": "重新读取图纸并依据可见证据判断。建议值不是事实；若图中不能确认则 needs_review。"
}
```

Stage 2/3 必须输出是否支持用户建议以及视觉证据。即使用户给了正确值，模型也不能无证据照抄。

## 6. Supervisor 与 Correction Workflow

### Supervisor Agent

- 理解用户是在直接修改、要求重新识别还是提出规则建议；
- 缺少项目、结果版本、连接 ID、工作区或字段时请求补充；
- 将自然语言转换为结构化 Correction Command；
- 不直接读取原图、不直接修改生产结果。

### Context Retrieval Tools

- `get_feedback_target(feedback_id)`；
- `get_connection_evidence(connection_id)`；
- `get_workspace_bundle(workspace_id)`；
- `get_stage_artifacts(business_run_id, stage, scope)`；
- `get_profile_snapshot(profile_key, version)`；
- `get_drawing_access(drawing_id)`。

这些是工具，不需要单独 Agent。

### Deterministic Correction Router

- 用户明确给出修改值时直接生成候选 patch，不调用 VLM；
- 没有跨页索引时选择目标 Drawing 的 Stage 2；
- 存在跨页索引时先复核 Stage 2 引用、重建 task，再执行单连接 Stage 3；
- 格式、排序、去重问题只执行确定性节点；
- 超出页面、成本或影响范围阈值时返回 Supervisor 请求用户批准。

### Extraction Workers

- 复用 Profile 的 Stage 1/2/3 Agent；
- 使用 correction context 和 scope allowlist；
- 输出新候选，不修改旧记录。

### Diff 与 Validator

由确定性代码执行：

- 字段级 before/after；
- 新增、删除、替换记录；
- 未关联记录 hash；
- 端子白名单、方向、电流单位、引用完整性；
- 受影响范围越界检测。

## 7. 当前项目提交

局部重提取完成后：

```text
Agent ResultPatchProposal
-> Server 业务校验和 expected_version
-> 前端展示字段级 diff、原图与证据
-> 用户接受 / 修改 / 拒绝
-> Server 创建 result_version + 1
-> feedback 标记 accepted/rejected
```

被拒绝的 proposal 也要保存，以便分析诊断 Agent 是否错误，但不能进入 Profile 改进正样本。

修订被接受后，Server 发送 `CORRECTION_ACCEPTED` 事件进入 Improvement Intake；Supervisor 不同步等待 Improvement 完成。

## 8. Improvement Harness

### 8.1 样本入口

只有以下反馈可以进入改进数据集：

- 已由用户接受；
- 目标记录、原图和证据可追溯；
- 不含未授权外部资料；
- 对应 Profile 和模型版本已知；
- 已完成原因标签或人工复核。

### 8.2 聚类

按以下维度形成 failure signature：

```text
profile_key + profile_version
affected_stage
root_cause_category
terminal/reference pattern
model snapshot
prompt checksum
```

单个案例只建立 regression case，不默认修改规则。相同 signature 达到阈值或属于高严重度问题时才创建 candidate。

### 8.3 候选类型

```text
PROMPT_PATCH
FEW_SHOT_ADD_OR_REPLACE
SCHEMA_PATCH
PROFILE_SIGNATURE_PATCH
REFERENCE_RESOLVER_PATCH
NORMALIZER_PATCH
VALIDATOR_PATCH
MODEL_CONFIG_PATCH
```

Prompt/Few-shot 可以由 Agent 生成候选。Python resolver、validator 等代码变更只生成结构化建议和测试案例，仍由开发流程实现与 review，V1 不允许 Agent 自动合并代码。

### 8.4 Eval Dataset

每个 Profile 的评测集分层：

```text
target_cases       本次要修复的问题
protected_cases    已稳定且不得回退的历史核心案例
negative_cases     空页、非线表页、无允许起点等
edge_cases         跨工作区、乱序跨页、缺失信息等
shadow_cases       未参与候选生成的留出集
```

测试比较 candidate 与当前 production baseline，不能只看 candidate 是否通过目标案例。

## 9. 指标和发布门禁

### 结构化指标

- Schema valid rate；
- Connection precision/recall；
- 起点端子精确率；
- 终点端子精确率；
- 方向正确率；
- 跨页引用解析成功率；
- 空页误提率；
- 重复记录率；
- `needs_review` 精确性；
- 来源证据覆盖率。

### 运行指标

- 每页/每连接 VLM 调用数；
- token、费用、P50/P95 耗时；
- 超时和重试率；
- 非法 JSON 率；
- 人工复核比例。

### V1 Gate

候选至少满足：

```text
target_cases 全部通过
protected_cases 无关键字段回退
negative_cases 零新增幻觉
schema valid rate = 100%
终点端子精确率不下降
费用和 P95 耗时不超过配置阈值
至少一名人工 reviewer 批准
```

LLM Judge 只能提供解释性评分，不能替代精确字段比较和人工审批。

## 10. 发布

```text
DRAFT
-> EVALUATING
-> REJECTED | APPROVED
-> CANARY
-> ACTIVE
-> RETIRED | ROLLED_BACK
```

- Profile 版本不可变，使用语义版本和 checksum；
- 旧 run 永远记录其原 Profile 版本；
- canary 默认只处理新任务，不能后台修改历史结果；
- 发现关键回退时自动停用 candidate 并回到上一个 ACTIVE；
- 历史项目如需新 Profile，必须由用户显式发起重新处理。

## 11. Harness 是否使用第三方框架

V1 建议：

- 使用现有 LangGraph 实现在线 StateGraph、checkpoint、interrupt 和子图；
- 使用 Pydantic 建立 Tool/Agent/Proposal Schema；
- 使用自建 provider-neutral Eval Runner 对比任意 OpenAI-compatible VLM；
- 使用 OpenTelemetry 或当前日志系统记录 trace；
- 可选接入 LangSmith 做可视化和评测，但业务正确性不能依赖 SaaS；
- 不引入额外的 AutoGen/CrewAI 式上层编排，避免与 LangGraph 双重状态管理。

这就是本项目的 Agent Harness：不是单一库，而是一套限制 Agent 如何读取、执行、评测和发布的工程边界。

Anthropic 的 evaluator-optimizer 模式适合有明确评价标准、且反馈能带来可测改进的任务；本项目的字段级标准答案和用户修订符合这一条件。但其建议同样强调保持简单、透明和工具边界清晰，因此普通提取继续使用确定性 Graph，不升级为自由规划 Agent。[Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)

## 12. 测试场景

### 在线修复

- 单个终点端子错误，只重跑一条连接；
- 起点漏提，新增连接并定向执行 Stage 3；
- 工作区反馈仅修改该工作区；
- 用户建议与图纸冲突，返回 needs_review；
- base result version 已变化，proposal 提交冲突；
- 重提取失败，旧结果继续可用。

### 离线改进

- 单个案例只进入回归集，不发布规则；
- Prompt 候选修复目标案例但破坏 protected case，自动拒绝；
- 新 Few-shot 提升准确率但费用超限，进入人工决策；
- validator 候选产生范围外变化，自动拒绝；
- canary 发生高严重度回退，自动 rollback；
- 已完成项目仍可按旧 Profile 重放。
