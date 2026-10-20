# API 入口归档

- [API2.16.0范围审核](./changelog/2026-10-20-bulk-review.md)：原子批量审核路由、当前批次/项目版本与OpenAPI/生成类型同步。

- [API2.15.0人工复核](./changelog/2026-10-20-connection-review.md)：版本化确认路由、当前批次待复核计数及OpenAPI/生成类型。

- [API2.14.0重扫需求](./changelog/2026-10-20-rescan-requirements.md)：requirements可选DTO兼容、新工具必填门禁、OpenAPI/前端类型同步，无migration。

- [API2.13.0主助手历史删除](./changelog/2026-10-19-assistant-history-delete.md)：204 DELETE、鉴权、Server事务和生成契约同步。

- [API2.12.0终点重扫目标绑定](./changelog/2026-10-19-rescan-target-bindings.md)：target_bindings与生成契约同步，需重载服务。

- [API2.11.0主助手接入](./changelog/2026-10-19-main-assistant.md)：安装受信会话/工具/确认路由，OpenAPI及Web契约同步；本地迁移已应用，当前进程需重载。

HTTP入口为apps/api/src/main.py，领域及持久化实现属于services/server。当前代码版本2.11.0，接入主助手会话/业务工具/确认；2.10.0提供项目全量XLSX二进制导出及Explain主动重扫边界；早期Explain鉴权SSE代理及生成契约，见[交付](../../service/server/changelog/2026-10-17-explain-proxy.md)；三表数据管理/原Auth契约见[Server说明](../../../services/server/README.md)及[交付记录](../../service/server/changelog/2026-10-16-simple-management.md)。

OpenAPI通过apps/api/scripts/export_openapi.py生成到apps/api/openapi.json，Web由openapi-typescript生成src/apis/generated.ts。batch_id/record_version替代旧结果版本和线号单元，不兼容旧业务写入DTO。上传入队、进度/SSE和重试已接入独立提取Worker，Supervisor仍未开放。见[增量交付](../../service/server/changelog/2026-10-16-incremental-extraction.md)。
