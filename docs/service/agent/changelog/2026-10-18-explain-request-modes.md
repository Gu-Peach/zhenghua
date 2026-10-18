# Explain自动解释与主动重扫边界

原默认查询返回整个项目当前批次最近5个重扫任务，使无关工作区的历史任务进入普通解释事实包。现在隐式查询同时限定当前conversation_id、project_id、actor和batch；显式rescan_id仍按项目/操作者权限读取历史单个任务。响应再次检查会话范围，异常数据不混入上下文。

ExplainTurn新增向后兼容allow_rescan=true，Web普通打开的自动解释及“解释已有任务差异”显式false：模型工具列表不含rescan_connections，执行工具时再次核验，模型即使返回该调用也不入队。重试沿用原turn权限，不扩大权限；用户主动输入/重扫按钮维持原有能力。Prompt明确普通获取依据/待复核标记不是重扫授权。前端项目历史入口由用户点击后才读取，不再在挂载时自动展示。

新增4项假网关/MockTransport测试，连同既有来源/编辑/检索/网关及2项重扫绑定用例共79项通过；Ruff、Explain包18源码mypy通过。DTO经export_explain_contract同步到Server，再生成OpenAPI与Web类型。未调用真实模型、创建实际重扫或改业务库。

启用需用户重载8000 API2.9.0和8100、刷新Web；无迁移或提取Worker改动。原默认true保持外部调用兼容，自动解释边界由受信客户端的false参数和工具执行校验共同限制。见[ADR-0035](../../../adr/0035-project-xlsx-export.md)。
