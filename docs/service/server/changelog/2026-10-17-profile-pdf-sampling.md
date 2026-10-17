# Profile PDF抽样代理

2026-10-17。API2.5.0新增`POST /api/v1/profile/drafts/{draft}/pdf-samples`，沿用JWT、内部令牌和`X-Profile-User-Id`代理到8100。输入包含草稿修订、幂等request_id、PDF文件名与Base64，stage固定classification；默认50MiB。返回草稿及抽样来源元数据，不返回或保存原PDF。

Agent负责抽样和草稿文件，Server不存Storage/业务表；发布机制及数据库Schema未改。生成Pydantic、OpenAPI和TS契约已同步，包括样图origin及ConversationState.pdf_sample。无需新迁移，加载新8000/8100代码后使用。

5项Profile Server测试通过，其中新增真实内存PDF/Mock代理测试验证Schema一致、JWT/跨用户拒绝、两页抽取、幂等、非法stage拒绝和对话恢复，无真实模型调用。2个Server源文件类型检查和源码Ruff通过。未启停服务或修改业务数据。
