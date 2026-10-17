# 规则聊天显示模型失败类别

2026-10-17。规则SSE错误除中文说明外，显示`code`和可选`diagnostic_id`。不再将HTTP拒绝、超时、截断和结构错误都显示为无法定位的通用提示；同轮请求ID、输入/图片和重试行为保持。

10项规则聊天回归通过；新增失败态用Mock SSE验证错误码/诊断编号和重试，另检查桌面/390px截图无溢出。TypeScript、lint、生产构建通过。截图在忽略目录`.runtime/profile-model-error-visual`。

后端需由用户重载8100启用错误分类与诊断。本轮未调用真实模型、重启服务或改业务数据。历史失败没有记录原响应，当前并未证实某一种模型错误为实际根因，见[Agent记录](../../../service/agent/changelog/2026-10-17-profile-model-errors.md)。
