# 规则会话删除

DraftStore使用现有metadata的deleted_at逻辑删除草稿。事务先核对所有者/修订，重复删除幂等；列表过滤墓碑，读取、创建重试和后续修改拒绝已删除草稿。保留草稿文件及历史修订，不接触发布包或项目数据。

新增 `DraftDeleteInput` 和 Agent `DELETE /v1/profile/drafts/{draft}`，成功204；Server生成DTO、公共OpenAPI和TS同步。完整语义见[设计与执行计划](../profile-conversation-management.md)。

验证：7项Agent路由离线回归通过（新增2项涵盖所有权、确认、另一窗口修订冲突、重复删除、重启保留、不可恢复写回、文件和历史保留）；新增删除用例模型调用数为0。5源码mypy和8源码/脚本/测试Ruff通过，Server4项离线桥接通过。未接触真实草稿/模型/业务数据库或启停用户服务，无新迁移；需重载8100。
