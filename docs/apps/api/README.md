# API 入口归档

HTTP入口为apps/api/src/main.py，领域及持久化实现属于services/server。当前代码版本2.9.0，新增项目全量XLSX二进制导出及Explain主动重扫边界；早期Explain鉴权SSE代理及生成契约，见[交付](../../service/server/changelog/2026-10-17-explain-proxy.md)；三表数据管理/原Auth契约见[Server说明](../../../services/server/README.md)及[交付记录](../../service/server/changelog/2026-10-16-simple-management.md)。

OpenAPI通过apps/api/scripts/export_openapi.py生成到apps/api/openapi.json，Web由openapi-typescript生成src/apis/generated.ts。batch_id/record_version替代旧结果版本和线号单元，不兼容旧业务写入DTO。上传入队、进度/SSE和重试已接入独立提取Worker，Supervisor仍未开放。见[增量交付](../../service/server/changelog/2026-10-16-incremental-extraction.md)。
