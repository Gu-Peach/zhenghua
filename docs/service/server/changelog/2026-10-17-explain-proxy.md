# Explain 鉴权流式代理

2026-10-17，API 2.2.0。POST /api/v1/explain/turns/stream接收生成Pydantic契约，验证Supabase JWT、项目所有者后，经已有AgentBridge转发8100。可信用户ID只由Server注入X-Explain-User-Id；浏览器正文不接受actor/user_id，伪造同名头也被覆盖。不新增数据库写入或迁移。

应用服务为explain_service.py，路由为explain_routes.py，explain_contract.py由Agent脚本生成；Server不依赖Agent执行代码。OpenAPI与Web生成类型同步，capabilities增加explain=true，旧Supervisor仍false。

新增4项离线测试：生成Schema一致、Server→Agent真实ASGI/Fake模型链路、JWT/项目/正文身份隔离、内部令牌/生产缺令牌/未配置模型、上游安全错误及OpenAPI。连同Explain/Harness/网关和全部Server回归共94项通过；没有真实数据库/模型调用或服务重启。

当前代码已装配，运行服务需重载8000和共享8100；见[Server README](../../../../services/server/README.md)。
