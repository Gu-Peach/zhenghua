# API2.12.0终点重扫目标绑定

RescanRequest新增target_bindings：connection_ids/drawing_page必填，workspace_code/pdf_page_number可选。仅fields=end，重复/越界连接拒绝。Agent导出Server DTO、OpenAPI与TS；主助手内部参数共享Explain绑定DTO，Server独立导入生成契约，不导入Agent运行时。

assistant_tools将绑定原样写入现有enqueue_connection_rescan请求JSON。Worker按任务项目快照核对目录/范围，保留原鉴权、任务固定、候选确认事务，无新数据库Schema。新增Mock API验证主助手到入队的绑定完整传递。

185项默认/51项显式集成跳过、19项浏览器分批及静态检查、实际产物只读Fake重放见[交付](../../agent/changelog/2026-10-19-rescan-explicit-targets.md)。加载需重载8000及Agent/Worker。未调用真实模型、创建实际任务或改业务数据。
