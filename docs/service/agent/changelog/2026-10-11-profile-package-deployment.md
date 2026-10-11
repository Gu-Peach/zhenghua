# Profile 资源包本地迁移与发布

日期：2026-10-11。用户启动 Supabase 后授权迁移。本记录更新此前[实施记录](./2026-10-11-correction-packages-implementation.md)的部署状态；不是全链路真实模型验收。

## 已执行

1. 确认目标为 `supabase_db_zhenghua_test` 的 `postgres` 数据库；未操作另一套 `vc_simulation_backend`。
2. 历史已有 22 份迁移，最新 `20261011000000`；新表和 Bucket 均不存在。
3. 以一个事务应用 `20261011010000_profile_resource_packages.sql`，同时登记 `supabase_migrations.schema_migrations` 的 version/name/statements；成功后通知 PostgREST 重载 Schema。未重放旧迁移、重置库或清理业务数据。
4. 创建 `profile_resource_packages`、RLS、不可变内容 trigger、active 唯一索引、发布/回滚 RPC 和私有 `agent-profile-assets` Bucket。
5. 核对当前本地 ZH 与 test0 的 Profile checksum 相同，再使用已存在的 Auth 用户作为 bootstrap 发布者，上传并发布 ZH 1.0.0。

绑定信息：

```text
profile: zh@1.0.0
source_profile_checksum: sha256:25b6d6ba7cc86a93293f9069dc189a24fe46e0077940d75ea259f6012dea19a9
package_checksum: sha256:d0790037030fc4d75396d76ce5c12561422dcfa66794ab89c4efcfd2c7e1b10d
status: active
bucket: agent-profile-assets (private)
prefix: zh/1.0.0/d0790037030fc4d75396d76ce5c12561422dcfa66794ab89c4efcfd2c7e1b10d/
```

## 实际核对

- 29 个资源文件重新下载并校验 checksum，另有顶层 manifest，Storage 共 30 个对象。
- 6 项绑定资源；展示接口素材为 22 个文本文件、7 个图片签名 URL。
- 下载后 frozen ProfileRef 与原本地 ProfileRef 相等，没有改 Prompt、Few-shot 或规则。
- Bucket `public=false`；RLS 已开启；anon 读取资源包元数据为 0 行。
- 发布 RPC 执行权限：anon=false、authenticated=false、service_role=true。
- test0 结果版本摘要前后相同：`d09e681a0d94abc07845ca998ad96693`。
- 全部线表连接摘要前后相同：`09d141b7e5f1e8637e29ec3488c2c13b`。

## 部署时修复

PostgREST 对 `RETURNS void` RPC 返回成功但空响应体；原客户端总调用 `response.json()`，出现“数据库已经提交、客户端报 JSONDecodeError”的故障窗口。先补 200/204 空响应回归，再修改 `SupabaseClient.rpc()` 对空成功响应返回 None。初次发布已经生效；幂等重试复用同一个包，不产生重复版本。6 项 Supabase 基础设施单元测试通过。

## 待用户加载运行服务

本次没有修改 `services/agent/.env` 或现有进程环境，没有停止/重启 API、Worker 或 Supabase。API 和 Worker 加载新代码时都需设置：

```powershell
$env:AGENT_PROFILE_PACKAGES_ENABLED="true"
```

启用之后，启动时加载 active 包；冻结的旧任务/历史结果仍可按原版本和 checksum 读取对应包。启用但无匹配包时明确失败，不静默使用其他本地规则。

未运行：真实模型、空库全量 migration 回归、候选 canary/rollback 全链路、Web/JWT 代理和 test0 人工纠错。非提取 run 接管/fencing 等此前限制仍然存在，不能把本次资源包部署称为所有 Agent 功能验收完成。
