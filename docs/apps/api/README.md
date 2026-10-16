# API 入口归档

HTTP入口为apps/api/src/main.py，领域及持久化实现属于services/server。当前版本2.0.0，三表数据管理/原Auth契约见[Server说明](../../../services/server/README.md)及[交付记录](../../service/server/changelog/2026-10-16-simple-management.md)。

OpenAPI通过apps/api/scripts/export_openapi.py生成到apps/api/openapi.json，Web由openapi-typescript生成src/apis/generated.ts。batch_id/record_version替代旧结果版本和线号单元，不兼容旧业务写入DTO。Agent/Supervisor正式提取后续接入，当前仅保存上传。
