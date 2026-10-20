# 一键审核当前范围

沿用[ADR-0043](../../../adr/0043-connection-review-and-inline-create.md)新增范围审核。API2.16.0提供 `POST /api/v1/projects/{id}/connections/review`，输入batch_id、expected_updated_at、workspace_id/drawing_id/search与confirmed=true，Idempotency-Key必填。

Server验证所有者与图纸/工作区归属，复用表格的搜索清洗，把目录ID转换为工作区和PDF物理页。新事务函数review_extraction_scope锁定项目和匹配待复核行，校验可写状态、活动批次及项目时间版本；一次提交全部分页结果，保留逐行before/after、人工复核时间/操作者、版本递增和幂等回执。端子字段、已审核行、旧批次与范围外记录保持。冲突整体拒绝，不产生部分审核。

返回project_id、batch_id、reviewed_count和idempotent。没有待复核记录返回0并保留幂等回执。搜索字段与线表一致：起点/终点端子、原理号、起点/终点描述；客户端分页offset不限制审核范围。

验证：23项Server API通过，覆盖权限/只读、跨工作区和未知图纸、非法确认/时间戳、范围转换及搜索清洗；4项隔离SQL通过，覆盖空数据/旧快照迁移、105条跨分页审核、范围外/旧批次/已确认行保护、审计和版本、幂等与搜索、整批冲突。Ruff通过；严格mypy三文件仍6个既有问题，HEAD shadow-file基线相同，无新增错误。未运行全仓/真实模型测试。

本地20261020020000迁移已通过限定脚本安装，容器项目标签zhenghua_test正确，业务三表摘要未变。Schema备份/回执位于忽略目录`.runtime/migrations/20261020020000-*`。未代用户审核任何实际记录或启停服务。当前8000只读核对为2.15.0，需要重载至2.16.0并刷新Web；本轮无需8100/Worker变化。

其他本地实例安装命令：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261020020000 --apply
```

其他环境按部署流程应用同一迁移；回滚先撤回新路由，再以新迁移删除函数，已审核状态/审计不逆向改写。
