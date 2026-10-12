# 业务 API

FastAPI 入口 `src/main.py`，领域/持久化代码属于 `services/server`。默认端口 8000；独立 Agent 保持 8100。启动与接口说明见 [Server README](../../services/server/README.md)。OpenAPI 生成物在 `openapi.json`，Web 生成类型在 `apps/web/src/apis/generated.ts`。

所有业务接口要求 Supabase access JWT；禁止用用户 UUID 代替鉴权。浏览器经 `/api/v1` 请求，服务端将已校验身份转发 Agent。不新增数据库表，不引用旧 `backend` API。
