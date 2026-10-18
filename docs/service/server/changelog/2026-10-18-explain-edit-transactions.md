# 2026-10-18 Explain 修改事务与确认接口

API2.7.0新增项目内修改方案列表、读取、确认/拒绝接口。浏览器只提交方案UUID、checksum和决定，不能提交字段补丁或操作者。Server验证JWT项目所有者，数据库再次检查所有者、状态、当前批次、完整范围及行版本；模型没有确认接口工具。

新增migration `20261018020000_explain_connection_edits.sql`，新增proposal表、RLS、项目/所有者索引、过期时间、请求/逐行before-after及回执审计。两个service-role RPC分别准备方案、确认/拒绝；helper不能由浏览器调用。方案准备不改线表，范围超过1000行整体拒绝，提交出现新增/删除/修改任一匹配行时整体拒绝。整组交换还保护图纸索引版本。重复确认返回原回执，不会再交换一次。

保留稳定行ID、批次、原提取证据，修改增加record_version和人工修订链接；默认整组交换同时交换来源/目标页及工作区索引。前缀改值的坐标预览遵循既有清理触发器，确保实际提交与显示一致。提取中/归档/过期/失权不能提交。

SQL在无网络、无业务卷的独立PostgreSQL临时容器运行，包含合成旧数据和空库新增迁移基础：6项场景验证完整交换/幂等、prefix边界、CAS/范围增长、权限/拒绝/过期、1000行上限/索引变化、RLS/显式空值；测试容器均清理，不在用户Supabase执行测试。

离线验收后，已在本项目本地`supabase_db_zhenghua_test/postgres`备份public Schema，仅部署新表/RPC并原子登记迁移历史；原profiles/projects/connection_rows三表摘要前后一致，未执行实际修改RPC或模型调用。PostgREST OpenAPI已出现prepare/decision两个RPC。备份及回执在忽略的`.runtime/migrations/20261018020000-*`。

部署脚本`services/server/scripts/apply_explain_edits_migration.py --apply`校验固定本地容器项目标签、拒绝历史内容不一致，默认不带--apply只核对状态。其他环境仍须先应用新迁移。现在仅需用户重新加载8000/8100，原启动参数不变，提取Worker无改动。契约顺序：Agent `export_explain_contract.py` → API `export_openapi.py` → Web openapi-typescript。
