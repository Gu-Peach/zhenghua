# 规范化线表数据库结构

日期：2026-10-09

## 变更

- 新增项目、项目成员、工作区、图纸和结果版本表。
- 新增端子排级 `wiring_units` 与端子明细级 `wiring_connections`，表达一个线号对应多条端子连接。
- 新增结果版本内从 1000 开始的事务安全线号分配器。
- 将原理号、电压等级、端子排、起终点代号/描述/端子、电流、备注和色标保存为可查询列。
- 为连接增加 `is_cross_page` 三态列，仅允许 `same_page`、`cross_page`、`unknown`；详细跨页引用仍由 evidence/阶段产物承载，不新增专用表。
- 新增连接证据表和 `wiring_connection_rows` 扁平只读视图，暴露项目名称、工作区名称和工作区业务页码。
- 新表包含外键、唯一约束、检索索引、更新时间触发器和成员只读 RLS。
- 旧 `wiring_tables.records` 未迁移、未删除，旧表结构没有修改。

## 验证

- 使用 PostgreSQL AST parser 验证两份 migration 语法通过。
- 静态契约检查确认 16 个请求字段、9 张新表、1000 起始线号逻辑均存在，且 migration 不包含旧表变更。
- 远端执行、真实 PostgreSQL 语义、RLS 与并发测试尚未运行，原因是当前环境只有 Supabase URL/service-role key，没有 DDL 所需的 CLI access token 或数据库连接。
