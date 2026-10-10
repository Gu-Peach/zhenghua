# Agent 数据库工作流落地

日期：2026-10-09  
状态：本地真实 Supabase 已验收

## 行为

- 完整提取 Proposal 自动创建 `draft` 或 `needs_review` 结果版本，并原子写入线号单元、连接明细和证据。
- 数据库按结果版本从 1000 分配线号；Agent 提取到的旧线号只保留在 raw payload，不作为正式线号。
- Supervisor 使用 `wiring_connection_rows` 做强类型检索；Correction bundle、图片 Storage 引用和用户问题持久化。
- 局部修订只生成 Proposal；用户明确确认后，受控 RPC 校验 base/record version 并创建新的 `accepted` 版本。
- accepted feedback、模型 Trace、Profile candidate、Release Gate、eval、人工审核、canary/active/rollback 审计全部持久化。
- 内部 feedback bundle 不授予浏览器直接读取权限；owner 仍可通过 RLS 读取线表视图。

## 数据库

- `20261009050000`：正式结果提交、feedback、Trace、candidate、eval 和审计表/RPC。
- `20261009060000`：Trace 同时支持 UUID Run 和 `improvement:/candidate:` 逻辑键。
- `20261009070000`：收紧内部 feedback payload 权限。

## 验证

- `verify_supabase_agent_database_workflows.py` 在真实本地 Supabase 上通过：版本 1 提取落库、线号 1000、查询、版本 2 纠错、accepted feedback、UUID/逻辑 Trace、candidate ACTIVE、eval 和审计。
- owner 能读取项目线表视图，但不能直接读取 `feedback_items`。
- 临时项目、用户、Storage 对象、候选和逻辑 Trace 已清理；旧 `wiring_tables` 仍为 4 条。
- Agent 测试 86 项通过；目标 Ruff、strict mypy、`compileall` 和 `supabase db lint` 通过。
