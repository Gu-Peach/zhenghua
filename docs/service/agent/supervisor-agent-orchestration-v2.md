# Supervisor 与专业 Agent 串联方案 V2

> 状态：Accepted for implementation  
> 日期：2026-10-09  
> 范围：Supervisor、Profile Detection、Correction、Improvement、受控数据库工具

## 1. Profile Detection 作为 Supervisor 内部工具

用户只与 `SupervisorAgent` 对话。Supervisor 在处理 PDF 时调用 `detect_profile(document_id)`；工具内部限制为 PDF 物理第一页，并复用 `ProfileRouterAgent` 的专用 Prompt、图片输入和结构化输出。

Supervisor 只接收 `profile_key / confidence / evidence / status`：

- 高置信且 Profile 可用于生产时，绑定不可变 Profile 版本/checksum 并继续三阶段提取；
- 低置信、UNKNOWN 或 experimental 时，由 Supervisor 向用户确认；
- 用户确认后恢复同一个等待中的 run，不创建重复任务。

`ProfileRouterAgent` 保留为内部模型组件，但不作为独立用户入口，也不直接维护对话。

## 2. 受控数据库工具与版本化修改

所有 Agent 共享同一组领域工具协议和 repository，但不暴露任意 SQL、表名或任意字段更新：

- `find_connections`：按项目、工作区、业务页码、线号、端子等条件查找候选，返回稳定 ID；
- `get_connection_bundle`：按 `project_id + result_version_id + connection_id` 读取当前记录、来源页、Profile 和版本；
- `create_result_patch_proposal`：保存字段级 before/after、证据、expected version 和 unchanged assertion；
- `commit_result_patch`：只允许业务 Server 在用户确认后调用，校验 base version 并创建新结果版本；
- `record_accepted_feedback`：提交已被用户接受的修订，供离线 Improvement 使用。

项目名称、工作区名称、线号和端子只用于搜索。出现多个候选时 Supervisor 必须追问；实际修订必须使用稳定 ID。Stage Agent、Supervisor 和 Improvement Agent 均不直接覆盖生产结果。

## 3. Correction 路由与 Stage 2/3

Correction Workflow 使用确定性矩阵，不增加自由规划 Agent：

| 场景 | 执行路径 |
| --- | --- |
| 用户给出明确正确值 | 直接生成 patch，不调用 VLM |
| `is_cross_page = same_page` 且需重新识别 | 只重跑目标连接所在页的 Stage 2 |
| `is_cross_page = cross_page` 且需重新识别 | Stage 2 复核来源引用，再按已有索引定向运行 Stage 3 |
| `is_cross_page = unknown` | Stage 2 重新判断；不足时 `needs_review`，禁止猜测 |
| 工作区/页面身份错误 | Stage 1 后按新的 `is_cross_page` 决定 Stage 2/3 |
| 格式、排序、单位或去重 | 只运行确定性工具 |

纠错上下文是结构化数据，包括 connection ID、允许字段、观察到的问题和证据引用；用户自由文本不能成为系统 Prompt，也不能扩大连接或字段 allowlist。

所有路径最终只生成 `ResultPatchProposal`。业务 Server 展示 diff，用户确认后用乐观锁提交新 `result_version`。

## 4. `is_cross_page` 三态字段

数据库和 Agent 契约只增加一个跨页字段：

```text
is_cross_page = same_page | cross_page | unknown
```

- `same_page`：Stage 2 已确认连接可在当前页完成；
- `cross_page`：Stage 2 已确认需要跨页目标，由现有 Drawing Index/阶段证据定位目标页；
- `unknown`：证据不足或尚未判断，需要复核。

该字段属于连接记录，由 Stage 2 写入候选结果。它不使用 boolean/null 混合表达，也不新增专用跨页引用表；详细引用继续保存在现有 evidence/阶段产物中。

## 5. Improvement、规则确认和发布门禁

在线修订成功后立即返回新结果版本，不等待根因分析。只有用户接受并由 Server 提交的修订才进入异步 Improvement：

1. `ImprovementDiagnoserAgent` 读取 before/after、原图证据、Stage 产物、Profile/Prompt/模型版本，判断模型感知、幻觉、Prompt、Few-shot、跨页规则、确定性规则、映射或证据不足；
2. 原因和改动建议返回 Supervisor 展示；
3. 若涉及规则，Supervisor 必须先取得用户对“创建规则候选”的明确确认；
4. `ProfilePatchBuilderAgent` 只修改隔离 Profile Sandbox；
5. Eval Runner 执行 target/protected/negative/edge/shadow 回归；
6. `EvaluationJudgeAgent` 解释差异，确定性 Release Gate 决定是否允许审批；
7. 人工 reviewer 批准后才能进入 Canary，严重回退自动回滚；
8. 历史 run 和结果继续绑定原 Profile 版本。

用户确认只授权创建候选，不等于直接修改或发布生产 Profile。

## 最终串联结构

```text
用户
  -> SupervisorAgent
     -> detect_profile tool -> ProfileRouterAgent
        -> 用户确认（必要时）
        -> PageClassifierAgent (Stage 1)
        -> PageScannerAgent (Stage 2, 产生 is_cross_page)
        -> CrossPageResolverAgent (Stage 3, 仅 cross_page)
        -> ResultProposal

  -> SupervisorAgent
     -> find_connections / get_connection_bundle
     -> Correction Workflow
        -> direct patch
        -> 或 Stage 2
        -> 或 Stage 2 -> Stage 3
        -> ResultPatchProposal
     -> 用户确认
     -> Server commit_result_patch -> 新 result_version
     -> record_accepted_feedback
     -> ImprovementDiagnoserAgent（异步）
     -> Supervisor 展示原因和建议
     -> 用户确认创建规则候选
     -> ProfilePatchBuilderAgent -> Profile Sandbox
     -> Eval Runner -> EvaluationJudgeAgent -> Release Gate
     -> Reviewer -> Canary -> Active / Rollback
```

## 权限边界

- Supervisor：意图识别、追问、工具调度和结果展示；无任意数据库写权限、无生产 Profile 写权限。
- Stage 1/2/3：只返回结构化候选结果；不提交数据库。
- Correction：确定性选择最小执行范围；执行阶段只生成 proposal，用户明确确认后才调用受控结果提交 RPC。
- Improvement：只处理 accepted feedback；不阻塞在线修订。
- Profile Patch Builder：只写候选沙箱。
- 受控提交层：数据库 RPC 执行 base version、项目范围、幂等和原子事务校验；当前内部 Supervisor 作为过渡调用方，`apps/api` 接入后由业务 Server 承担外部鉴权入口。
