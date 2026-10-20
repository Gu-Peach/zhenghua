# API2.11.0 主助手入口

应用宿主安装新的assistant routes，持久化/权限/工具和确认逻辑仍位于 `services/server`，不把模型或长任务放入路由层。OpenAPI与Web生成Client已同步；旧管理、Explain、Profile和兼容端点保留。

新增接口、迁移和测试见[Server交付](../../../service/server/changelog/2026-10-19-main-assistant.md)。本地迁移已安装，当前运行中的8000 OpenAPI仍是2.10.0，需要用户重启现有命令加载2.11.0，并同步重载8100后试用。未自动启停正在运行的服务。
