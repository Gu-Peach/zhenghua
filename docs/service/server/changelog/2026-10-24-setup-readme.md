# 项目安装与启动说明

## 交付

- 根目录 `README.md` 覆盖依赖安装、Supabase CLI 初始化/启停/升级、三表及辅助表说明、四个应用进程、环境变量、登录用户和数据库规则包初始化、检查与排错。
- 当前 Agent 明确使用 `src.extraction_main:app`，独立 Worker 与 inline 模式二选一；普通工作台无需旧直连数据库启动器。
- `supabase/scripts/create_tables.ps1` 默认调用 CLI 预览本地未应用迁移，显式 `-Apply` 才执行；失败立即停止并恢复工作目录。复用全部 46 份现有迁移及 CLI 历史，不复制表结构或修改历史 SQL。
- `create_buckets.sql` 补建缺失的私有 `project-assets` / `agent-profile-assets`，不覆盖已有配置和文件；不符隐私/MIME 要求则回滚并报告。`verify_setup.sql` 只读检查表/RLS/RPC/bucket/迁移历史，不读取用户业务行。
- 更新 `supabase/README.md`、文档索引、TODO 和 roadmap；保留各模块历史交付记录，根 README 明确当前运行方式。

## 验证

- 根 README 与数据库 README 本地链接和 Markdown 围栏检查通过。
- 本机 Supabase CLI 2.90.0 的 `db push --local --dry-run`、`migration up --local` 参数经帮助输出核对；安装方式另核对 Supabase 官方文档。
- PowerShell 解析通过；在 `.runtime/readme-validation` 的独立夹具内以假的 CLI 验证缺配置拒绝、默认只预览、显式应用、预览失败阻断、应用失败传播、成功/失败后恢复工作目录。没有真正调用 CLI/数据库。
- 只读检查脚本中 18 张表和 7 个 RPC 签名与迁移核对；RLS 声明静态核对，助手四表的循环启用语句人工复核。
- `git diff --check` 通过。SQL 仅静态审阅，未声称完成 PostgreSQL 执行验证。

## 限制和运行边界

Docker daemon 当前不可连接，未执行全新 Supabase 安装、空库/旧数据迁移、bucket SQL 或完整服务联调。未启动/停止实际服务、改业务数据、发布规则或调用模型。没有改前端/API/Agent 业务代码，因此未运行前端构建/截图或业务测试集。

历史迁移 `20261014010000` 会不可逆删除旧业务表；已有数据先备份评审，手工部署且历史缺失的数据库先核对历史。本文没有运行 `db reset`，没有改变 Schema/API/Profile 或宣称上线阶段完成。
