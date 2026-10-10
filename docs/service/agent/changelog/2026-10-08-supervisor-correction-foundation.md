# Supervisor 与 Correction 架构及契约骨架

日期：2026-10-08

## 决策

- Supervisor 是用户对话的唯一 Agent 入口，负责意图结构化、缺失信息追问和向 allowlist 中已注册的工作流分派命令。
- Profile Detection、Extraction、Correction、Improvement 是受限子工作流；子 Agent 返回候选结果，不直接写生产业务数据。
- 在线纠错由确定性 `CorrectionRoutePlanner` 根据反馈类型、目标范围和跨页索引选择直接 patch、确定性校验、Stage 2 或 Stage 2 + Stage 3。
- 不设置独立的 Remediation/Triage/Planner Agent。用户接受修订后再交由 Improvement 流程分析根因；Improvement 不在本次实现范围内。
- Supervisor 的聊天上下文不承担长任务状态；run、checkpoint 和阶段事件是持久任务状态的来源。

## 实现

- 新增 Supervisor、Correction、Improvement 领域模型和意图/工作流枚举。
- 新增 `SupervisorAgent` 意图决策、缺失字段追问和受约束工作流命令。
- 新增 `WorkflowRegistry`，只分派显式注册的处理器。
- 新增确定性 `CorrectionRoutePlanner` 和单元测试。
- 保留旧 `SCOPED_REMEDIATION` 枚举作为兼容值；新契约使用 `SCOPED_CORRECTION`。
- 删除尚未投入使用的 Remediation 专属模型/Graph 占位包。

## 验证

- Agent 单测与契约测试：37 passed。
- `mypy --strict`：55 个源码文件通过。
- Ruff check/format：通过。
- 旧后端回归：53 passed，2 skipped。

## 未完成与门槛

- M4 真实 VLM 评测仍未完成，因此 M5 尚未正式进入实现阶段。
- Supervisor StateGraph、事件到对话消息的映射、持久会话 API、子工作流执行器和 Server 集成仍待后续里程碑。
- 本次没有调用付费 VLM，也没有改变旧 ZH 提取链路。
