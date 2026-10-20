# 主助手会话、业务工具与确认

8000 API版本为2.11.0，实现 [ADR-0039](../../../adr/0039-main-assistant-orchestration.md) 的受信业务入口。

## 接口和数据

- `/api/v1/assistant/capabilities`：实际检查新表和8100能力，未就绪时不伪造可用状态。
- `/api/v1/assistant/conversations`、`/{id}`：按所有者隔离的会话和历史分页，每页最多50轮。
- `/{id}/attachments`：用户发送后保存私有图片/PDF，图片复用已有8MB/2000万像素限制，PDF不超过50MiB。客户端不提供Storage路径。
- `/{id}/turns/stream`：冻结本轮界面范围，启动幂等轮次并保存公开事件。完成事件在持久化之后发送；恢复可从已存action补回中断时未传到浏览器的任务卡。
- `/api/v1/assistant/actions/{id}`、`/{id}/decision`：重读原候选/差异，并由用户确认；模型工具表没有decision。
- `/api/internal/assistant/turns/{id}/tools`：服务凭据及临时轮次token校验。调用者不能提供另一个用户身份；已结束或被接管的轮次token不能执行工具。

新增 `assistant_conversations/turns/actions/attachments`，RLS只允许authenticated读取自己的元数据，写入和RPC仅限service_role。轮次通过租约阻止并发，复用turn_id时检查请求摘要；工具action ID由轮次、工具和规范参数确定。正式行和规则事实仍在原业务表，action只保存查询引用或原提案/任务标识，不复制整份线表。

## 专业流程

项目/工作区/图纸检索从授权项目的实际索引读取，包含零记录工作区，业务编号归一化只用于匹配。导航返回真实ID，不能由模型输出任意路由。

重扫直接复用 `enqueue_connection_rescan`、现有Worker及确认服务。all工作区/页沿用replace_scope，单行/单侧沿用patch。参考图必须映射PDF物理页，关联页作为参考不会缩窄或扩张替换范围。当前重扫沿用历史冻结规则，不将数据库最新包自动替换进旧项目。

规则诊断优先原任务冻结ZIP，严格检查路径、包摘要和资源清单；没有冻结产物时只能读项目精确绑定的存储版本并标注证据缺口，不能回退到最新包。本人规则的建议从当前可编辑最新版本产生。确认校验action摘要、proposal差异及基线，应用后人工确认准确修订，再沿用既有发布事务；发布失败可从已审阅修订继续，不重复应用diff。非本人规则只读诊断，不能借此越权发布；自动派生他人包不在本次工具范围。

项目删除沿用“先归档、清Storage、再删数据库”策略，补入绑定到该项目的assistant附件路径；失败保留归档项目供重试。未绑定项目的会话附件保留在所属用户会话中。

## 迁移和验收

新增 `supabase/migrations/20261019020000_main_assistant.sql`，在无网络的独立Postgres容器中分别对空库和旧项目快照执行，两项通过；包含RLS、跨用户拒绝、RPC权限、租约接管、旧token失效、幂等重放及请求冲突。

已用明确本地容器 `supabase_db_zhenghua_test` 应用，确认项目标签；原项目、规则、线表指纹不变。部署回执及迁移前Schema备份位于 `.runtime/migrations/20261019020000-*`，不提交。已通知PostgREST刷新缓存。

其他环境使用：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261019020000 --apply
```

该脚本只允许明确的本地项目容器，不能用它部署任意远程数据库。回滚会丢失主助手历史/引用；先备份，按迁移注释删除本次两RPC、四表与触发函数，并按用户会话前缀清理Storage；不删除正式线表或Profile。

Server全量默认测试分批累计73通过、46个显式集成测试跳过；本次SQL两项另外显式通过。主助手/解释/规则适配及项目删除已覆盖，API/TypeScript契约重新生成，静态检查通过。未请求真实模型、未创建真实重扫或改生产规则。
