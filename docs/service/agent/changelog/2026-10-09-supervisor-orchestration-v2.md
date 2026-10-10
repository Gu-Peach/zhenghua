# Supervisor 串联 V2 与三态纠错

日期：2026-10-09

## 实现范围

- 将 `ProfileRouterAgent` 封装为 Supervisor 可调用的首页 Profile Detection 工具；低置信、UNKNOWN 或 experimental 结果继续等待人工确认。
- 新增受控结果工具及 repository 协议，支持按项目、工作区、业务页码、线号和端子组合查找，准备纠错证据包、乐观版本提交及 accepted feedback 记录；不接受任意 SQL、表名或字段更新。
- 为 Stage 2 连接结果增加 `is_cross_page = same_page | cross_page | unknown`，并按三态确定性选择 Stage 2/3 局部重识别路径。
- 明确答案直接生成最小 `ResultPatchProposal`；重识别仍只生成 proposal，用户确认后才执行版本提交。
- 提交后的 accepted feedback 自动进入 `ImprovementDiagnoserAgent`；Supervisor 向用户展示脱敏原因和建议，只有明确授权后才运行 `ProfilePatchBuilderAgent`。
- Profile 候选只写隔离沙箱，随后由 Eval Runner、`EvaluationJudgeAgent`、确定性 Release Gate 和人工 reviewer 控制发布。

## 契约与数据库

- 增加受控检索、纠错准备和结果提交 Pydantic 契约，并更新 domain schema checksum。
- 新增独立 migration，为 `wiring_connections` 增加三态 `is_cross_page`、约束、索引和扁平视图字段；没有新增跨页专用表。
- 数据库线号仍由结果版本内计数器从 1000 分配，Agent 不生成生产线号。

## 验证

- 70 个不依赖 PyMuPDF 的 pytest 通过。
- 5 个 PDF/图像相关测试在项目 `.venv` 中通过，包括 Fake Extraction Worker、独立三阶段流程和原生多模态 Stage 适配器。
- Supervisor 全链路测试覆盖：直接修订、proposal 确认、结果版本提交、accepted feedback、诊断、用户授权、沙箱候选、评测 Judge 和 Release Gate。
- 新增/变更 Agent 文件的定向 Ruff、12 个核心文件 strict mypy、`compileall` 和 domain schema snapshot 通过。
- 两份线表 migration 均通过 PostgreSQL AST 解析。
- 未调用付费 VLM，也未停止、重启或修改用户正在执行的真实提取进程。

## 尚未完成

- 受控结果 repository 当前为进程内开发适配器；生产 Supabase 事务、项目权限、持久审计和 Server 事件代理仍待 `apps/api/services/server` 接入。
- migration 尚未应用到远端 Supabase；当前环境缺少可执行 DDL 的 CLI access token 或数据库连接。
- ABB 独立规则/真实回归资产、生产队列和完整跨进程恢复仍按现有 M8/M15/M16 待办推进。
