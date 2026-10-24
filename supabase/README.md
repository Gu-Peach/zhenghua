# 数据库与 Storage 安装

完整安装、环境变量、四进程启动和首次规则发布见[根目录 README](../README.md)。当前数据库依赖 **Supabase PostgreSQL + Auth + Storage + PostgREST**；不是旧 `wiring_tables` 单表模式，也不能只装普通 PostgreSQL。

## 脚本入口

| 路径 | 用途 |
| --- | --- |
| [`migrations/`](migrations) | 唯一的版本化表结构、索引、RLS、事务 RPC 和 bucket 创建来源 |
| [`scripts/create_tables.ps1`](scripts/create_tables.ps1) | 调用 Supabase CLI 预览或执行本地待应用迁移，保留 CLI 迁移历史 |
| [`scripts/create_buckets.sql`](scripts/create_buckets.sql) | 补建缺失的私有 bucket，不覆盖已有配置/文件/策略 |
| [`scripts/verify_setup.sql`](scripts/verify_setup.sql) | 只读核对关键表/RLS/RPC/bucket/迁移历史，不读取用户数据 |

`scripts/*.sql` 是运维辅助脚本，不由迁移工具自动运行，不替代 `migrations/`。在 Studio SQL Editor 粘贴执行，或使用 `psql -v ON_ERROR_STOP=1 -f <文件>`；不依赖 psql 专属的 `\i` 指令。

## 全新本地实例

从仓库根目录执行；Docker Desktop 必须已经运行：

```powershell
if (-not (Test-Path supabase\config.toml)) { supabase init }
# 启动前核对 project_id、端口、Auth site_url、Storage 上限和 seed 配置，见根 README
supabase start
supabase status
.\supabase\scripts\create_tables.ps1
.\supabase\scripts\create_tables.ps1 -Apply
```

首次 `start` 会应用迁移；脚本用于预览/补齐剩余迁移，不重复执行已经登记的版本。当前迁移终点为 `20261020020000_bulk_connection_review.sql`。后续新增迁移自动由同一目录管理，无需修改入口脚本。

**禁止把旧实例当作空库套用：** `20261014010000` 会删除 18 张旧业务表及旧视图，数据不可逆；已有数据必须先备份并评审。手工部署导致迁移历史缺失时，先核对历史，不能靠重跑所有 SQL 或 `db reset` 修复。`db reset` 会重建数据库。

已有实例使用原配置运行 `supabase start`，检查 `supabase migration list --local` 和脚本预览，再决定升级。日常停止用 `supabase stop`，不加 `--no-backup`。

## 当前数据库模型

核心表为 `extraction_profiles`、`extraction_projects`、`extraction_connection_rows`，创建定义在 [`20261014000000`](migrations/20261014000000_create_simple_extraction_business_tables.sql)。后续迁移添加坐标、增量提取、修改/重扫、规则发布、助手会话和人工复核。

Agent 运行数据继续使用 `agent_*` 表；`connection_*` 记录方案/重扫，`assistant_*` 记录助手会话及附件清理，`profile_asset_gc` 记录规则包清理。完整清单及创建脚本链接见根 README，字段/权限以迁移为准。`verify_setup.sql` 的检查结果不是端到端业务测试。

## Storage

- `project-assets`：当前工作台私有桶，默认 500 MiB；包含 PDF、PNG/JPEG、JSON、XLSX 和规则 ZIP。上传还受 Storage 全局上限及 API 的 200 MiB PDF 上限约束。
- `agent-profile-assets`：旧 Agent 私有规则资源桶，保留兼容；当前规则 ZIP 放在 `project-assets/profiles/...`。
- `images`：早期迁移留下的公开桶，当前工作台不使用。补建脚本不创建或修改它，不自动删除其中历史文件。

完整迁移已创建 bucket 并设置相应策略。补建脚本只在缺失时插入，已有公开权限或 MIME 不兼容会报错回滚；上限等实际配置由只读检查展示，由管理员评审调整。不得为修复预览而开放业务 bucket。service-role key 仅供 API/Worker，浏览器使用后端授权的短期签名 URL。

## 验证状态

2026-10-24 新增启动文档及辅助脚本，原 migration 内容不变。本次进行了入口/配置/CLI 参数及静态检查；Docker daemon 当前不可连接，未执行全新实例安装、空库/旧数据迁移或真实模型测试，也未改变现有业务数据库。
