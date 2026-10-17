# Explain 共享宿主与公开工具事件

2026-10-17。现有src.extraction_main改为独立Agent共享宿主：保留可选inline提取Worker/health，新增Explain HTTP/SSE。无新增端口，不启用旧Supervisor；Explain按需装配，模型缺配置不阻塞health或Worker，调用时安全返回503。可信身份依赖首先验证内部令牌，再读取Server的UUID用户头。生产令牌缺失拒绝请求。

Graph初始检索及模型工具调用发送tool_started/tool_completed/tool_failed，公开参数经过Schema校验，结果只包含已允许的行/证据/签名图片地址和安全错误，不包含原始参数、内部思考或图像base64。现有context/retrieval/answer_delta/completed保留，消费者需支持新事件先于context。

公共DTO通过scripts/export_explain_contract.py从Agent模型生成Server适配器，并用Schema测试验证一致；Server OpenAPI生成Web类型。前端独立浮窗见[Web交付](../../../apps/web/changelog/2026-10-17-explain-panel.md)。

Explain、网关/Harness及Server共94项离线测试通过，13份相关Agent源码strict mypy和Ruff通过。未调用真实模型/数据库、未改提取规则或业务数据、未自动重启既有服务。实际使用需按[启动说明](../../../../services/agent/README.md)运行8100共享宿主；单独Worker可以继续独立运行，HTTP宿主无需再启inline Worker。

## 后续启动排障

同日用户报告来源解释返回503。核对8000健康，8100无监听；截图启动的是incremental_worker，只领取提取任务，没有HTTP接口。当前配置的Agent地址确为127.0.0.1:8100，数据库/模型配置存在且两端内部令牌一致（仅比较标志，不输出凭据）。

已后台补启动src.extraction_main:app，AGENT_INLINE_WORKER=false，保留用户现有Worker，不重启8000。后台进程PID记录在.runtime/explain-http/server.pid，输出日志stdout.log/stderr.log同目录，均不提交。AgentBridge经现有配置GET /health成功，worker_running=false；OpenAPI注册Explain流路由，使用内部鉴权的空输入POST返回422，未进入数据库/模型调用。用户可重试原浮窗，真实模型回答仍未代跑。
