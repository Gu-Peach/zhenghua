# ADR-0004：Agent 结果持久化与受控提交边界

状态：Accepted  
日期：2026-10-09

## 背景

Agent 的 Run、Event、Artifact、Proposal 与 Storage 已接入 Supabase，但完整提取结果仍只停留在 `result_proposals`；Supervisor 的结果查询、Correction bundle、accepted feedback、Profile candidate 和 eval 仍使用进程内仓库。服务重启后，纠错和规则演进链路无法继续，数据库也不是完整的业务事实来源。

## 决策

1. 完整提取通过受控数据库 RPC 原子创建 `result_versions`、`wiring_units`、`wiring_connections` 和 `connection_evidence`。写入状态为 `draft` 或 `needs_review`，不会未经用户确认直接成为 `accepted`。
2. 局部修订仍先生成不可变 `ResultPatchProposal`。只有 Supervisor 收到明确的用户确认后，才能通过同一受控 RPC 创建新结果版本；RPC 校验 base version、record version、项目归属和 proposal 幂等键。
3. Agent 不接受任意 SQL、表名或字段更新。Python 适配器只把强类型 Proposal 映射为数据库定义的规范化 payload。
4. `feedback_items` 持久化 Correction bundle、before/after、操作者和 accepted feedback；Profile candidate、评测、门禁结果和状态审计分别持久化。
5. Profile 文件修改仍只发生在隔离沙箱。数据库保存候选 patch、checksum、评测和审核状态；未经确定性门禁和人工审核不得激活。
6. service-role key 仅存在于 Agent/Server 进程环境。浏览器只能经业务 API 或受 RLS 保护的只读查询访问数据。
7. 当前 Agent 内部 Supervisor 可在明确确认后调用受控提交适配器，作为 `apps/api` 尚未完成期间的生产过渡。后续业务 Server 接入时复用相同 RPC，并成为外部用户请求的事务入口。

## 结果

- 数据库成为提取、纠错和规则演进状态的事实来源，Worker 重启不丢失关键状态。
- 完整提取失败不会留下半个结果版本；相同 Proposal 重试返回同一结果版本。
- 用户修订与规则建议保持分离，生产 Profile 不会被单次反馈直接改写。

## 不采用

- 在 Worker 中逐表 REST 插入：中途失败会产生不完整结果，无法满足原子性。
- 继续仅保存整包 Proposal JSON：无法分页检索、定位证据或执行行级版本校验。
- 让模型直接调用任意数据库工具：无法保证权限、字段白名单、幂等和审计。
