# API2.15.0人工复核

新增 `POST /api/v1/connections/{connection_id}/review` 与SimpleConnectionReview，回执action扩充review，项目读取增加needs_review_count。OpenAPI和Web生成类型同步；版本/权限/幂等及事务验证见[Server交付](../../../service/server/changelog/2026-10-20-connection-review.md)。本地迁移20261020010000已安装，需重载8000并刷新Web。本轮无Agent契约或8100/Worker变化。
