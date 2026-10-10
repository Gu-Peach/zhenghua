# Server 服务文档

业务 Server 是项目、工作区、图纸、结果版本、线表、反馈和权限的事实所有者。当前仓库尚未创建目标 `apps/api`，本目录先记录数据库与后续 Server 实现契约。

## 当前数据库工作

- 旧 `public.wiring_tables` 保持迁移期只读，不修改历史结构。
- 新规范化结构由 [`supabase/migrations/20261009000000_create_normalized_wiring_schema.sql`](../../../supabase/migrations/20261009000000_create_normalized_wiring_schema.sql) 定义。
- Agent runtime、私有 Storage、原子队列、规范化结果提交、反馈和 Profile 演进状态由 `20261009020000` 至 `20261009070000` migration 定义；本地 Supabase 已应用全部 migration。
- 字段语义和线号分组规则见 [ADR-0002](../../adr/0002-normalized-wiring-records.md)。
- Agent 已用新结构持久化运行控制面、源 PDF、页面图片、阶段产物、规范化结果、反馈和规则候选。当前内部 Supervisor 可在明确确认后调用受控提交 RPC；未来业务 Server 应复用同一事务边界并承担外部鉴权与授权。

## 当前限制

- 本地真实 Supabase 已完成 migration、owner/anon RLS、签名 URL、并发事件序号、checkpoint 乐观锁和 1000 起线号分配冒烟；托管远端环境尚未部署和复验。
- 旧 `wiring_tables` 与旧公开 `images` Bucket 保持不变；历史数据回填脚本与带旧数据快照的完整迁移报告尚未完成。
- `apps/api`、面向 Web 的分页查询、上传会话、SSE 代理和导出服务尚未实现；底层结果提交 repository/RPC 已完成。
