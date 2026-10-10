# Agent Runtime、Supervisor 与受控改进链路

日期：2026-10-09

## 实现范围

- 增加 Run 控制面、Worker、进程内队列、阶段 Artifact/Event、SSE、取消、恢复和 `ResultProposal`。
- 将三阶段提取接入 Worker；阶段事件来自实际工作流进度，产物先保存再发 completed 事件。
- 增加 Supervisor Graph、受控 Workflow Registry、用户可读事件映射，以及文档处理、纠错、状态查询、规则查询和确认输入处理器。
- 增加 Correction Workflow：直接字段 patch 不调用 VLM；局部重提取复用 Stage 1-3；在 proposal 前执行版本、范围、起点保护和 unchanged assertion 校验。
- 增加 Improvement Diagnoser、Profile Patch Builder、Evaluation Judge、Profile Sandbox、Eval Runner 和确定性 Release Gate。
- 增加候选审批、canary、审计和回滚状态机；未获人工批准的候选不能进入 canary/active。

## 契约与安全

- 扩展 Run、Correction、Improvement、Candidate 和 Eval Pydantic 契约，并更新 domain schema checksum。
- Agent 内部 API 支持可配置 Bearer token；非 development/test 环境缺少 token 时拒绝启动受保护调用。
- HTTP Run 只接收受控 source-document 引用，不接收任意本地路径。
- Profile Sandbox 拒绝路径逃逸和符号链接逃逸；代码类修改只保留为建议，不自动合并。
- Agent 仅生成结果或规则候选，不写生产业务结果。

## 验证

- `.venv` 下 13 个 `unittest` 通过，覆盖 Run/Worker、SSE、鉴权、取消竞态、Supervisor、Correction、发布门禁、Profile 沙箱、Fake 三阶段 Worker 和原生 VLM 适配器。
- 系统 Python 下 63 个非真实 VLM `pytest` 通过。
- 新增文件定向 Ruff 检查通过，`compileall` 通过，domain schema snapshot 通过。
- 未调用付费 VLM；用户正在执行的真实 ZH 提取进程未停止、未重启、未修改。

## 尚未完成

- Run/Event/Artifact/Proposal/Candidate/Eval repository 与 queue 当前为进程内适配器，不能跨进程或服务重启恢复；生产持久实现和独立 Worker 后端仍待基础设施决策。
- M8 仍缺完整中断续跑矩阵和 ZH 固定案例字段级/耗时/费用报告。
- ABB Profile 仍混有 ZH `XD` 白名单，缺少经人工确认的独立真实回归资产，因此 M15 保持阻塞。
- 仓库没有 `apps/api`，Web 仍使用 Mock Supervisor，M16 的会话持久化、事件代理、权限和真实 UI 闭环保持阻塞。

