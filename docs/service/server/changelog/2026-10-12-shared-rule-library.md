# 共享且直接可用的规则库

日期：2026-10-12。决策见 [ADR-0012](../../../adr/0012-shared-ready-rule-library.md)。

## 行为

- 手工上传/创建的规则包不再有 draft 阶段，写入后为 active；所有 authenticated 用户可读取文字资源和 Server 签名图片。
- 同一 key 可保留多个 active 不可变版本；规则库和 Agent 新任务选择最新版本，冻结任务继续按 checksum 读取历史包。
- 规则库每个 key 只展示最新可用版本，删除仍限创建者并转 retired。
- `profile_candidates` 关联的隔离包不属于共享规则库，仍仅创建者/审核者可见并保留评测确认流程。

## 数据库

- `20261012000000_shared_rule_library_read.sql`：删除单 active 索引、旧非候选 draft 升 active、移除 draft 状态、共享读取并调整发布 RPC。
- `20261012010000_scope_shared_rule_read.sql`：把共享 RLS 精确限定为 `candidate_id is null`，避免暴露隔离候选。
- `20261012020000_profile_package_multi_version_rollback.sql`：候选回滚只停用目标候选包并恢复其 base，不再误停用同 key 的其他可用版本。
- 三个 migration 已应用到本地 Supabase 并登记。非创建者 authenticated 验证可见五个手工包、候选为零；空库和合成旧数据的全部 27 个 migration 重放通过。

未修改项目、线表或用户数据，未调用真实模型，也未停止现有服务。运行中的 Server/Agent 需要由用户重载才能使用新代码与 ABB adapter。
