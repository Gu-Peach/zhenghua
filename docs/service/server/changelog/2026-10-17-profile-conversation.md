# Profile 对话鉴权代理

2026-10-17。业务API升级2.4.0，新增草稿对话GET与SSE POST：

- `GET /api/v1/profile/drafts/{draft}/conversation`
- `POST /api/v1/profile/drafts/{draft}/conversation/turns/stream`

继续使用Supabase JWT，由Server注入`X-Profile-User-Id`并携内部令牌代理8100。Agent校验草稿所有者，用户不能通过正文传入身份。流返回进度、公开答复和持久状态；不增加端口、业务表或发布权限。Agent SDK另外提供非流式对话接口供离线/服务端调用。

Pydantic契约由Agent AST导出到独立Server适配器，OpenAPI及TS已同步。4项Profile代理/发布测试通过，新增对话测试核对三个公共Schema一致、JWT/跨用户拒绝、流事件及恢复，使用Mock传输和临时草稿。2个Server源文件类型检查、源码Ruff通过。未启停用户服务、写真实业务库或运行付费模型。

重新启动8000加载2.4.0，并重新加载8100的新增路由后使用；发布沿用原迁移，本轮没有新迁移。若草稿接口404，检查运行进程OpenAPI，不能只刷新前端。
