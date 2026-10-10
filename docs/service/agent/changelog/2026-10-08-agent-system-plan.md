# 2026-10-08 Agent 系统规划

## 新增

- Agent 与业务 Server 独立部署，Agent API 默认端口 `8100`；
- Profile Detection、Extraction、Remediation、Improvement 四类 Graph；
- 专用 Agent、确定性节点和受控 Tool Registry 的协作边界；
- Server-Agent 异步 run、事件和 ResultProposal 契约；
- 连接、图纸、工作区级局部重提取；
- 问题根因分类与最小重跑矩阵；
- Provider-neutral Agent Harness；
- 候选 Profile 沙箱、回归评测、人工审批、canary 和 rollback。

## 决策

- 业务 Server 是生产结果事实来源；Agent 不能直接覆盖业务数据。
- 在线修复与离线规则改进隔离。
- ZH 现有三阶段 Graph 通过 Compatibility Adapter 渐进迁移。
- UNKNOWN Profile 不自动提取。
- V1 不允许 Agent 自动修改或发布 Python 代码。
- ABB 必须使用独立原图、规则和回归集，不能复用 ZH 样本冒充支持。

## 待评审

- Agent runtime 是独立数据库还是同库独立 schema；
- Queue 采用 Redis/Celery、Postgres 队列或其他方案；
- Profile 自动选择阈值；
- canary 比例和回滚阈值；
- 是否部署 LangSmith，或仅使用本地 trace/eval。
