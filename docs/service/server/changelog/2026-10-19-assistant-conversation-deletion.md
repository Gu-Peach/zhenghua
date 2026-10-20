# 主助手历史对话永久删除

用户要求在历史列表逐条提供×，直接从数据库删除。实现遵循[删除边界设计](../assistant-conversation-deletion.md)。

- API2.13.0增加鉴权 `DELETE /api/v1/assistant/conversations/{conversation}`，成功204，重复请求幂等；其他所有者404、活动轮次/上传409。数据库函数与begin_turn锁定同一会话行。
- 新迁移 `20261019050000_assistant_conversation_deletion.sql` 原子删除会话并级联turn/action/attachment元数据，将私有附件先写入 `assistant_asset_gc`。Server立即尝试清理，暂时失败保留队列，后续同一用户的删除/历史列表请求重试，每次最多20个；只允许service_role访问队列。
- 保留项目、正式线表、Profile和独立任务；删除历史不会撤销已提交的业务修改，也不会取消独立任务。
- 不可恢复的历史删除只在用户点击对应×后执行，本轮安装迁移不调用任何实际删除RPC。

## 验证与启用

- 先补HTTP失败测试，复现旧接口405；新增6项HTTP场景覆盖物理删除、重复提交、越权/未登录/活动轮次、Storage失败后重试及路径隔离。全套Server默认测试107通过、53项显式集成跳过，无模型调用。
- 显式临时Postgres中2项SQL场景通过：空库/旧快照安装、角色权限、活动轮次/上传保护、非法路径整笔回滚、物理级联/清理队列、独立数据保持和删除后旧轮次失效。临时库和独立容器已清理。
- 修改源码Ruff与3文件strict mypy通过，OpenAPI/TS重新生成，前端typecheck/lint/build与12项主助手浏览器测试通过。截图在 `.runtime/assistant-conversation-deletion/`，不提交。
- 已通过原限定脚本安装本地迁移，Schema备份/回执位于被忽略的 `.runtime/migrations/20261019050000-*`。业务三表和主助手四表摘要均未改变。
- 只读确认当前8000已为2.13.0且DELETE接口存在；刷新Web即可。不需因本轮修改重载8100或提取Worker，无新环境变量。

其他实例先安装该迁移，再加载新版8000/Web：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261019050000 --apply
```

测试命令（仓库根目录）：

```powershell
.\.venv\Scripts\python.exe -m pytest services/server/tests -q -p no:cacheprovider
$env:ASSISTANT_SQL_TEST='1'
.\.venv\Scripts\python.exe -m pytest services/server/tests/test_assistant_deletion_sql.py -q -p no:cacheprovider
```

Storage清理采用持久队列的一致性策略，并非跨数据库/Storage分布式事务；用户后续打开历史列表会继续清理暂时失败或超过20个的剩余附件。回滚不能恢复用户已永久删除的历史。
