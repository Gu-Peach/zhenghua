# API2.16.0范围审核

新增 `POST /api/v1/projects/{project_id}/connections/review`，SimpleBulkReview/Receipt同步至OpenAPI和Web生成类型。范围审核包含当前目录/搜索全部分页，带活动批次、项目版本、所有者与幂等保护，本地20261020020000已安装，需重载8000并刷新Web，见[Server交付](../../../service/server/changelog/2026-10-20-bulk-review.md)。
