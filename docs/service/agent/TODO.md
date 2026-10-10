# Agent 服务开发 TODO

> 状态：执行基线  
> 最后更新：2026-10-09  
> 实现目录：`services/agent`  
> 原则：严格按里程碑顺序开发；前一阶段未通过验收，不进入后一阶段。

## 1. 执行规则

- 同一时间只允许一个里程碑处于 `in progress`。
- 每个子 Agent 先完成 Schema、Fake Model 测试和失败路径，再运行付费 VLM 验收。
- 默认测试禁止调用真实 VLM；真实模型测试必须显式开启并记录模型、耗时、费用和案例摘要。
- 子 Agent 只返回结构化候选结果，不直接写业务数据库。
- Graph 中的索引、排序、去重、diff、版本检查和发布门禁使用确定性代码。
- ZH 的三阶段运行时与确定性工作流已迁入 Agent 包，旧 `backend/` 保留为迁移期链路；ABB 必须使用独立 Profile 和独立回归集。
- M4 的付费首页评测是生产启用门槛，不阻塞使用 Fake Model 开发 Stage 1-3。
- 每个里程碑完成后更新本文件、`docs/TODO.md`、`docs/roadmap.md` 和 Agent changelog。

## 2. 总体顺序

| 顺序 | 里程碑 | 状态 | 主要结果 |
| --- | --- | --- | --- |
| M0 | Agent 服务模块骨架 | done | 可独立启动和测试的 `services/agent` |
| M1 | 公共领域契约与运行时接口 | done | Run、Event、Profile、Proposal、Repository Protocol |
| M2 | Harness 最小底座 | done | Model Gateway、Tool Registry、Context、Trace、Checkpoint |
| M3 | Profile Registry 与兼容适配器 | done | 可加载版本化 Profile，并包装现有 ZH 流程 |
| M4 | Profile Router 子 Agent | done | 首页识别、人工确认与动态 Profile 绑定；真实 VLM 评测另作生产门槛 |
| M5 | Page Classifier 子 Agent | done | Stage 1 单页身份分类 |
| M6 | Page Scanner 子 Agent | done | Stage 2 当前页连接扫描与跨页引用占位 |
| M7 | Cross-page Resolver 子 Agent | done | Stage 3 单连接定向补全 |
| M8 | Extraction Workflow 集成 | in progress | Run/Worker/SSE/Proposal 离线链路完成；跨进程持久化、完整断点测试和真实 ZH 基线待完成 |
| M9 | Supervisor 主 Agent | offline foundation done | 对话 Graph、受控分派和事件反馈已实现；生产会话持久化待 M16 |
| M10 | Correction Workflow | offline foundation done | 直接 patch、局部重提取、diff 和 ResultPatchProposal 已实现；真实数据适配器待 M16 |
| M11 | Improvement Intake 与问题归因 | offline foundation done | 已接受反馈校验、根因分类和失败签名已实现 |
| M12 | Profile Patch Builder 子 Agent | offline foundation done | Profile 沙箱候选补丁和代码变更隔离已实现 |
| M13 | Evaluation Judge 子 Agent | offline foundation done | 确定性评测指标、Judge 解释与硬门禁优先级已实现 |
| M14 | Improvement Workflow 与 Release Gate | offline foundation done | 人工审批、canary、审计和回滚状态机已实现；持久发布后端待接入 |
| M15 | ABB Profile 接入 | blocked | 现有 ABB Stage 2 仍含 ZH XD 白名单，缺少经人工确认的独立真实回归资产 |
| M16 | Supervisor/Server/Web 集成 | blocked | `apps/api` 尚不存在，业务持久化、事件代理和 Web 真实 API 尚未建设 |

## 3. M0：Agent 服务模块骨架

状态：`done`

### 实现

- [x] 创建 `services/agent/pyproject.toml` 和 `src/agent_service` Python 包。
- [x] 按架构建立 `api/application/domain/graphs/agents/tools/harness/infrastructure` 模块目录。
- [x] 建立 `profiles/zh`、`profiles/abb` 和 `tests/unit|integration|contract|profile_regression` 目录。
- [x] 实现 FastAPI 应用工厂与 `GET /health/live`。
- [x] 实现 `GET /health/ready`，逐项报告配置、Profile Registry、运行时存储和模型配置状态。
- [x] 增加 `.env.example`、结构化配置、日志和本地启动命令。
- [x] 增加最小 lint、类型检查和 pytest 配置。
- [x] 在 `services/agent/README.md` 记录安装、启动和验证方式。

### 验收

- [x] `services/agent` 不导入旧前端，也不直接导入业务 Server 内部实现。
- [x] 未配置 VLM 时进程仍可启动：`live=200`，`ready` 明确返回依赖未就绪。
- [x] 配置完整时 `ready=200`。
- [x] OpenAPI 可生成，健康检查具有契约测试。
- [x] lint、类型检查和默认 pytest 全部通过。

退出条件：Agent 服务可在 `8100` 独立启动，且尚未包含任何伪造的业务成功结果。

## 4. M1：公共领域契约与运行时接口

状态：`done`

### 实现

- [x] 定义 `RunType`、`RunStatus`、`Stage`、`ScopeType` 和稳定错误码。
- [x] 定义 `AgentRun`、`RunScope`、`AgentEvent`、`ArtifactRef`、`ProfileRef`。
- [x] 定义 `ResultProposal`、`ResultPatchProposal`、operation、validation 和 unchanged assertion。
- [x] 定义 `FeedbackTarget`、`Diagnosis`、`CorrectionPlan`、`CorrectionContext`。
- [x] 定义 `RunRepository`、`EventRepository`、`ArtifactRepository`、`CheckpointStore` Protocol。
- [x] 固化 JSON 序列化、版本字段、时间格式和错误响应。

### 验收

- [x] Pydantic Schema 覆盖 Server-Agent 契约中的示例和非法输入。
- [x] proposal 缺少 base version、证据或目标 ID 时校验失败。
- [x] domain 层不依赖 FastAPI、数据库 SDK 或具体模型供应商。
- [x] Schema 生成指纹快照并加入契约测试。

退出条件：后续所有 Agent、Graph 和工具都只依赖这组稳定契约。

## 5. M2：Harness 最小底座

状态：`done`

### 实现

- [x] 实现 provider-neutral `ModelGateway`，支持 OpenAI-compatible VLM。
- [x] 实现 `FakeModelGateway`，覆盖成功、超时、非法 JSON 和 Schema 错误。
- [x] 实现 Tool Registry 和每个 Agent 的工具 allowlist。
- [x] 实现 Context Builder 和可重放的 Context Manifest。
- [x] 实现 checkpoint、trace、event 接口及开发期内存适配器。
- [x] 实现重试分类、超时、取消检查、调用预算和敏感字段脱敏。
- [x] 以 `run_id + graph + node + item_id` 实现 checkpoint 幂等键。

### 验收

- [x] 默认测试不发出外部网络请求。
- [x] 暂时性错误按策略重试，Schema/权限/配置错误不盲目重试。
- [x] 同一幂等键重复执行不会重复生成事件或产物。
- [x] trace 可记录模型、Agent、上下文元数据、耗时和重试次数；后续子 Agent 负责补充 Profile/Prompt/输入引用。

退出条件：任一子 Agent 都能在受控模型、工具、上下文和追踪环境中执行。

## 6. M3：Profile Registry 与兼容适配器

状态：`done`

### 实现

- [x] 定义 `DrawingProfile` Protocol 和 Profile package manifest。
- [x] 实现 Profile Registry、版本解析、checksum 和不可变快照。
- [x] 统一校验 manifest 中声明的 Prompt、Few-shot、Schema、validator 和 eval 文件引用。
- [x] 建立 ZH Compatibility Adapter，读取当前稳定 Prompt 和规则。
- [x] 将旧 `wiring_graph.py` 包装为受控调用，不复制或重写已验证算法。
- [x] ABB 先注册为 `experimental`，未通过回归前不可用于生产提取。

### 验收

- [x] 缺文件、越界资源和重复版本会阻止 Profile 激活；快照保存资源 checksum。
- [x] ProfileSnapshot 不可变，run 可绑定具体版本和 checksum。
- [x] ZH 适配器参数/结果转换测试通过，旧后端回归保持 `53 passed, 2 skipped`。

说明：M3 未调用付费 VLM，也未改变旧 ZH 提取算法；真实图片字段级回归在 M5-M8 接入新子 Agent 时执行。

退出条件：公共 Graph 可通过统一接口使用 ZH，且没有供应商条件分支。

## 7. M4：Profile Router 子 Agent

状态：`done`

### 实现

- [x] 只渲染 PDF 物理首页，不读取后续页面。
- [x] 为每个 Profile 定义可版本化、可公开查看的结构化识别与提取规则摘要。
- [x] 将所有已注册 Profile 的识别规则动态注入一次 VLM 请求。
- [x] 实现 `ProfileRouterAgent` 结构化输出候选、分数、首页证据和原因。
- [x] 支持 `PROFILE_SELECTED` 和 `WAITING_INPUT`；识别失败时生成面向用户的选择问题。
- [x] 支持用户确认后锁定 Profile 版本/checksum，并保留自动判断和确认人记录。
- [x] 生成统一 `ProfileBinding`，供三阶段 Extraction Graph 动态读取 Prompt、Few-shot 和规则。
- [x] 提供 Profile 公开规则查询接口，供前端展示。

### 验收

- [x] ZH 首页、ABB 首页和未知模板负例均有固定测试。
- [x] 低置信、未知 key 和 experimental Profile 不得静默进入提取。
- [x] Fake VLM 覆盖 ZH、ABB、未知、非法 JSON 和人工确认。
- [x] 验证真实 PDF 首页渲染只访问第 1 页。
- [x] Fake Model、边界输入和首页渲染的离线验收通过。

当前状态：Profile Router 组件和离线契约验收完成。真实 VLM 首页识别评测保留为生产启用门槛，记录在 Agent Release Gates，不阻塞阶段 Agent 开发。

退出条件：只有确认过的 Profile 能进入 Extraction Graph。

## 8. M5：Page Classifier 子 Agent（Stage 1）

状态：`done`

### 实现

- [x] 定义强类型分类请求/结果，明确保留 PDF 物理页号与图纸业务页号。
- [x] 输入限制为单页原图、已锁定 Profile 和可选已知页面上下文。
- [x] 空白页走确定性短路；封面、目录、非原理图和不确定页面按 Profile 分类。
- [x] 按 `ProfileBinding.adapter` 分发；ZH adapter 调用现有 `classify_page`、Prompt、图片 Few-shot 和 parser。
- [x] 为分类 Agent 建立独立 StateGraph 入口。

### 验收

- [x] 单页、空白页和 Profile adapter 未注册均有测试。
- [x] 分类输出始终包含输入的 PDF 物理页号，并保留 VLM 置信度、原因和复核标记。
- [x] 默认测试使用 Fake Stage Adapter，不调用真实 VLM。

退出条件：分类阶段可独立调用、测试和审阅，并能传递给后续索引构建。

## 9. M6：Page Scanner 子 Agent（Stage 2）

状态：`done`

### 实现

- [x] 定义强类型页扫描请求/结果；每次只处理一个当前来源页，不接收目标页图片。
- [x] 提取该页可见连接、起终点、线号/放线标记、电流及引用证据。
- [x] 跨页连接保留已确认起点与引用，终点为空；不在 Stage 2 推测目标页内容。
- [x] 按 `ProfileBinding.adapter` 分发；ZH adapter 调用现有 `scan_page`、Prompt、图片 Few-shot 和 parser。
- [x] 空白页/非原理图页确定性输出空 units，不消耗 VLM 调用。
- [x] 为页扫描 Agent 建立独立 StateGraph 入口。

### 验收

- [x] Adapter 调用、空页短路、单页输入和页号保护有 Fake tests。
- [x] 输出 PDF 物理页号与输入一致；Profile 资源版本随请求绑定。
- [x] ZH 图片 Few-shot 从原 Profile 路径加载，不复制或降级成纯文本样本。
- [x] Schema 错误由阶段子图失败返回，不伪造成功的空提取。

退出条件：Stage 2 产物可独立审阅，并能由确定性代码生成跨页任务。

## 10. M7：Cross-page Resolver 子 Agent（Stage 3）

状态：`done`

### 实现

- [x] 定义单条跨页任务请求，包含来源页、索引指定的目标页、connection/task context 和 Profile。
- [x] 仅根据输入任务定向补全终点及允许字段；请求与输出均不含可变更起点的接口。
- [x] 按 `ProfileBinding.adapter` 分发；ZH adapter 调用现有 `resolve_cross_page`、Prompt、图片 Few-shot 和 parser。
- [x] 空白目标、没有可确认终点时返回 needs_review，不猜测终点；缺失目标在请求 Schema 处拒绝。
- [x] 为 resolver 建立独立 StateGraph 入口；确定性跨页任务构建仍在 Agent 外执行。

### 验收

- [x] 来源页 + 一个或多个索引目标页的定向任务可用 Fake Stage Adapter 测试。
- [x] 空白目标、无可确认终点时输出 needs_review。
- [x] 结果不包含 start 字段，保证 Stage 3 无法改写已确认起点。
- [x] ZH 跨页样本路径及图片输入保持与现有 few-shot 完全一致。

退出条件：每条跨页任务可独立重放，且不会修改起点或无关连接。

## 11. M8：Extraction Workflow 集成

状态：`in progress`

### 实现

- [x] 本地 runner 串联 PDF render、Stage 1、确定性 Drawing Index、Stage 2、跨页任务、Stage 3、校验及 JSON/XLSX 产物。
- [x] 文档级编排迁入公共 Graph；`zh_workflow` 的规则、domain、PDF、checkpoint 和导出实现迁入各自模块。新增非空字段、跨页和 checkpoint 恢复回归；正式入口不依赖兼容包。
- [x] 删除用户确认不需要的相邻页分段、批量提取及专属辅助代码，并在后续清理中删除整个 `zh_workflow` 兼容目录与旧 import 转发。
- [x] 接收锁定的 ProfileBinding，并逐阶段读取 Profile 绑定的 Prompt/Few-shot。
- [x] 每阶段先写 ArtifactRepository，再发 Agent Run 事件；开发使用内存适配器，Supabase 模式已有持久 Run/Event/Artifact/Proposal/Checkpoint 与原子结果提交。
- [x] 迁入页级并发、模型重试、JSON checkpoint 断点恢复、失败隔离、任务取消检查和 Run 创建幂等。
- [x] 转换为 `ResultProposal` 并通过 Agent HTTP API/Worker 对外执行；本地脚本不写生产线表。
- [x] 提供 Run 创建/查询/取消/恢复、事件查询/SSE、Artifact 与 Proposal 查询 API。

### 验收

- [ ] 单页已有 Fake Model Worker Graph 测试；多个工作区、空页、非连续业务页号和乱序跨页组合仍需补齐。
- [ ] 进程中断后完整续跑测试覆盖所有阶段，已完成 item 不重复调用模型。
- [ ] ZH 完整 PDF 结果、耗时和费用相对旧基线有对比报告。

退出条件：完整三阶段提取可恢复、审计并生成 proposal。

## 12. M9：Supervisor 主 Agent

状态：`offline foundation done`（生产会话持久化与 Server/Web 闭环归 M16）

说明：Supervisor/Correction 架构、领域契约、意图决策骨架和确定性纠错路由已建立；此里程碑负责完整对话 Graph 与事件反馈。

### 实现

- [x] 定义 ConversationTurn、SupervisorIntent、SupervisorDecision、WorkflowCommand 和用户事件契约。
- [x] 实现意图决策骨架与 allowlist Workflow Registry。
- [x] 将子工作流阶段事件转换成用户可读消息，不把长任务状态只存于聊天上下文。
- [x] 将 ProfileRouterAgent 封装为 Supervisor 的首页 Profile Detection 内部工具；低置信、UNKNOWN 和 experimental 结果保持人工确认。
- [x] 将 Improvement 归因原因、建议和候选状态转换为脱敏用户事件，不暴露原始反馈、证据、Prompt 或候选文件内容。
- [x] 用户文本作为不可信数据，仅能生成 allowlist 中的工作流命令，不得改变系统 Prompt 或 Profile 文件。

### 验收

- [x] 图纸处理、修订、查询状态、查看规则、确认输入和模糊请求均有受控路由实现。
- [x] Supervisor 不具备生产数据库写权限，也不直接调用 VLM 提取端子。
- [x] 子工作流失败、等待输入、进度和完成事件能稳定映射为对话响应。
- [ ] Fake Model 覆盖意图冲突、Prompt injection、目标缺失和用户确认。

退出条件：所有用户请求都先经过 Supervisor，专业子 Agent 不直接维护用户会话。

## 13. M10：Correction Workflow

状态：`offline foundation done`（真实 Server repository 适配器待 M16）

### 实现

- [x] 通过受控结果工具按项目、工作区、业务页码、线号或端子查找候选，再以稳定 ID、结果版本和连接 ID 定位目标；出现多条时要求 Supervisor 追问。
- [x] 实现确定性 Correction Router：直接 patch、Stage 2、Stage 2 + Stage 3、Stage 1 重建或纯确定性节点。
- [x] 使用 `is_cross_page = same_page | cross_page | unknown` 路由局部重识别：同页只运行 Stage 2，跨页运行 Stage 2/3，未知先由 Stage 2 重判。
- [x] 复用 M5-M7 子 Agent，不复制另一套提取逻辑。
- [x] 生成字段级 before/after、证据、预算、范围限制和 unchanged assertion。
- [x] 输出 `ResultPatchProposal`，由 Server 乐观锁校验并创建新结果版本。

### 验收

- [x] 用户直接改值不调用 VLM，并有最小字段 patch 测试；完整纠错矩阵仍需真实案例补齐。
- [ ] 单条跨页错误只复核相关 Stage 2 引用并重跑单连接 Stage 3。
- [x] base version、范围白名单和 unchanged assertion 在 proposal 前做确定性校验；Agent 不直接写旧结果。
- [x] 不存在独立 Remediation Agent、Feedback Triage Agent 或 Remediation Planner Agent。

退出条件：人工反馈可安全转化为最小范围候选修订，在线链路不依赖自由规划 Agent。

## 14. M11：Improvement Intake 与问题归因

状态：`offline foundation done`（生产反馈读取与持久化适配器待接入）

### 实现

- [x] Intake Schema 只接收已由用户接受并由 Server 提交的新结果版本。
- [x] 证据包包含原结果、Stage 产物、Profile/模型版本和 before/after diff 引用。
- [x] 输出模型感知、Prompt、Few-shot、跨页 resolver、确定性规则、映射、Profile 路由或来源不足分类。
- [x] 单案例默认只生成 regression case，不自动修改生产 Profile。
- [x] 生成稳定 failure signature，供聚类和候选创建使用。

### 验收

- [x] 未接受或证据不完整的修订不会进入改进数据集。
- [ ] 每个根因分类至少一个固定案例。
- [x] Improvement Diagnoser 无生产 Profile 或业务结果写权限。

退出条件：在线修数据与离线改规则完全隔离。

## 15. M12：Profile Patch Builder 子 Agent

状态：`offline foundation done`（候选 repository 当前为进程内实现）

### 实现

- [x] 只接收已接受、可追溯且完成根因标签的反馈集合。
- [x] 在 Profile Sandbox 生成 Prompt、Few-shot、Schema 或规则候选 diff，并拒绝路径逃逸/符号链接逃逸。
- [x] Python resolver/validator 代码仅生成建议和失败测试，不自动合并代码。
- [x] 候选记录来源反馈、生成原因、基线版本和 checksum。

### 验收

- [x] Tool allowlist 无生产 Profile 写权限。
- [x] 单次反馈不会触发生产发布。
- [x] 候选补丁可审阅、可拒绝、可重复评测。

退出条件：改进建议始终停留在隔离沙箱并具有完整来源。

## 16. M13：Evaluation Judge 子 Agent

状态：`offline foundation done`（真实模型评测数据集仍需 Profile 资产补齐）

### 实现

- [x] Eval Runner 支持分别执行 baseline 和 candidate，并生成逐案例结果。
- [x] 数据契约支持 target、protected、negative、edge 和 shadow cases。
- [x] 确定性代码计算字段级精确率、召回率、幻觉、Schema、费用和延迟。
- [x] Judge 只解释差异、风险和发布建议，不决定发布。
- [x] 输出可机器读取的 Eval Report 和可人工阅读的摘要。

### 验收

- [x] 候选只修目标但破坏 protected case 时由确定性 Gate 判定失败。
- [x] 新增幻觉、Schema 回退或关键字段下降时由确定性 Gate 判定失败。
- [x] Judge 结论与硬指标冲突时以确定性 Gate 为准。

退出条件：任何 Profile 候选都有可复现的基线对照报告。

## 17. M14：Improvement Workflow 与 Release Gate

状态：`offline foundation done`（生产发布存储和部署执行器待基础设施接入）

### 实现

- [x] 串联 accepted feedback、诊断、沙箱、候选生成、评测和发布建议。
- [x] 在线结果提交后异步触发 ImprovementDiagnoser；只有用户明确授权后才允许 ProfilePatchBuilder 写候选沙箱。
- [x] 实现确定性 Release Gate 和至少一名人工 reviewer 审批。
- [x] 实现 `DRAFT -> EVALUATING -> APPROVED -> CANARY -> ACTIVE` 生命周期。
- [x] 实现 canary 严重回退自动停用和回滚状态转换。
- [x] 候选发布不修改历史 run 的 Profile 绑定，也不后台重算。

### 验收

- [x] 无人工批准无法进入 CANARY/ACTIVE。
- [x] 回归、成本或延迟超过阈值会阻止发布。
- [x] rollback 会恢复上一 ACTIVE 版本指针，历史结果不变。
- [x] 发布、拒绝和回滚均有审计事件。

退出条件：自完善形成受控、可测试、可回滚的 Profile 发布闭环。

## 18. M15：ABB Profile 接入

状态：`blocked`

阻塞：现有 ABB Stage 2 Prompt 仍包含 ZH 的 `XD` 起点白名单；仓库内没有足以人工确认独立端子规则、正负例与跨页 expected JSON 的 ABB 真实资产。在修正并验收这些资产前保持 `experimental`，不得启用生产提取。

### 实现

- [ ] 使用 ABB 原图建立签名、Stage 1/2/3 Prompt 和图片 Few-shot。
- [ ] 按圆圈放线标志实现 ABB 独立引用解析和确定性规则。
- [ ] 建立 ABB 正例、负例、跨页、空页和边界回归集。
- [ ] 校准 Profile Router 对 ZH/ABB 的混淆阈值。
- [ ] 通过完整 Extraction 与局部 Correction 验收后发布 ABB Profile。

### 验收

- [ ] ABB 不复用 ZH 的端子白名单、引用规则或 Few-shot。
- [ ] 新增 ABB 不修改公共 Graph 拓扑。
- [ ] ZH protected cases 零回退。
- [ ] ABB 输出满足统一 Connection/Proposal 契约。

退出条件：第二种图纸标准以独立 Profile 接入，证明模块化设计成立。

## 19. M16：Supervisor/Server/Web 集成

状态：`blocked`

阻塞：仓库当前没有 `apps/api`，`apps/web` 仍使用 Mock Supervisor；缺少业务数据库 repository、跨进程队列、会话持久化和 Server 事件代理，因此不能把内存 Agent 适配器伪装成生产闭环。

### 实现

- [ ] 实现 Server 到 `POST /v1/supervisor/turns` 的内部鉴权和幂等调用。
- [ ] Server 持久化 conversation/turn，并代理 Agent run 事件。
- [ ] 前端 AI 对话框展示阶段消息、WAITING_INPUT、确认操作和 proposal diff。
- [ ] 支持刷新恢复、事件断线续传、任务取消和权限校验。
- [ ] Supervisor 不向 Web 暴露内部 token、签名 URL、Prompt 或完整 trace。

### 验收

- [ ] 图纸处理和线表修订都能从聊天界面发起并实时看到阶段反馈。
- [ ] 未授权用户无法读取项目会话、图纸、规则或任务事件。
- [ ] 用户确认可恢复对应 WAITING_INPUT run，不创建重复任务。
- [ ] Agent 离线或失败时旧结果仍可使用，前端显示可操作错误状态。

退出条件：Supervisor 成为唯一用户交互入口，Server 和 Web 完成可靠事件闭环。

## 20. 每个里程碑的交付模板

完成任一里程碑时必须附带：

```text
实现范围：
新增/变更契约：
Fake Model 测试：
真实 VLM 测试（若执行）：
固定案例与字段级结果：
耗时/费用变化：
失败与恢复路径：
文档与 changelog：
剩余风险：
下一里程碑是否允许开始：yes/no
```
