# 文档索引

## 产品与架构

- [产品需求](./frontend.md)：用户、导入、项目树、结果展示和反馈要求。
- [总体重构方案](./refactor-plan.md)：目标架构、数据模型、模块边界和迁移策略。
- [Agent 流程图生成 Prompt](./agent_flow_diagram_prompt.md)：用于生成流程示意图。

## 开发管理

- [开发路线](./roadmap.md)：按阶段组织的交付路径与退出条件。
- [TODO](./TODO.md)：当前执行清单和待决策问题。
- [CHANGELOG](./changelog/README.md)：已发生的产品和架构变化。

## 模块归档

- `docs/apps/web/`：React + Vite 前端设计、验收和阶段记录。
- `docs/apps/api/`：FastAPI 入口应用记录。
- [docs/service/agent/](./service/agent/README.md)：独立 Agent 服务、Graph、Harness 与 Profile 记录。
- `docs/service/server/`：领域服务和基础设施适配器记录。

## 维护规则

1. 开工前阅读产品需求、重构方案和当前 TODO。
2. 新任务开始时将可交付事项放入 TODO 的“进行中”。
3. 代码完成后更新 TODO；影响行为或架构时同步更新 CHANGELOG。
4. 路线阶段状态变化时更新 roadmap，不能只在聊天中说明。
5. 重大且难以逆转的技术决策应新增 `docs/adr/NNNN-title.md`。
6. 文档中的 `done` 必须有代码、迁移或测试结果支撑。
