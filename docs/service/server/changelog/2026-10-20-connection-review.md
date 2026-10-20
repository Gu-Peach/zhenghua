# 人工复核与目录状态

按[ADR-0043](../../../adr/0043-connection-review-and-inline-create.md)实现。`POST /api/v1/connections/{id}/review` 输入 record_version、confirmed=true 和 Idempotency-Key。独立RPC锁项目及行，校验所有者、生命周期、当前批次和版本，清除 needs_review、递增记录版本，保存 before/after 与人工确认时间。原始 evidence 与端子值不变；重复请求返回原回执，变更输入/过期版本拒绝。

项目列表/详情增加 needs_review_count；读取当前批次全部待复核行，覆盖完成图纸的复核标记，不依据前端搜索/分页或旧批次判断，失败/未完成页原状态保持。Web从子图纸聚合工作区状态；项目生命周期 status 仍使用既有枚举。

验证：22项Server API测试通过，包含权限、处理期只读、非法确认、旧批次隔离、超过1000条的全量聚合与失败页状态；新增2项显式隔离SQL测试通过，覆盖空库/带旧数据迁移、事务版本/权限/幂等/审计/活动批次。Ruff通过。严格mypy三文件检查有6个既有问题；使用HEAD shadow-file对比，数量和代码位置对应，新增代码无新增错误。未运行全仓测试或真实模型。

本地新增迁移20261020010000已通过限定脚本安装，容器项目标签匹配zhenghua_test；安装前后业务三表摘要一致。Schema备份与回执在忽略目录 `.runtime/migrations/20261020010000-*`。未代用户确认任何行、修改端子或启停运行服务。

其他环境先安装本迁移，再重载8000至API2.15.0并刷新Web；本轮无需重启8100或Worker（前序Agent改动的重载要求仍独立适用）：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261020010000 --apply
```

脚本只允许指定本地容器/迁移，备份Schema并比较业务数据摘要。其他部署环境应按其受控迁移流程执行同一SQL。回滚先撤回API路由，再用新迁移删除函数；已确认状态与审计不逆向改写。
