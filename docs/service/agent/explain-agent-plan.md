# Explain Agent 实施计划

2026-10-20 required兼容修订（代码/离线验收完成，真实JSON决策待复试）：现场HTTP400/provider_code=tool_choice_not_supported。仅命中明确不支持tool_choice的400时，Explain补调改用Pydantic判别联合的JSON决策（重扫/查询/看图/追问），不发送tools/tool_choice/response_format；解析后仍走原工具/Pydantic参数/权限/幂等/候选确认门禁。只在该轮保持结构化模式，检索后按已更新事实继续，沿用8次工具总预算；收到真实任务后直接展示回执。其他400/鉴权/供应方故障不降级，任意正文、伪造工具、非法Schema均不执行。不自动重试或改动已有queued任务。

2026-10-20执行补调修订（代码/离线验收完成，真实供应方待复试）：现场两次正常stop均无tool_calls，首次校验只是阻断假成功，尚未完成工具执行。ModelRequest新增可选tool_choice=required，仅Explain缺回执补调及其待完成检索轮使用，普通问答/其他Agent默认保持。补调上下文使用当前结构化行、图纸索引、原查询分页和最新用户需求，不重复历史原始提取产物；所有参数仍经原Pydantic工具/repository鉴权与候选门禁。供应方忽略required时明确失败，不能将正文解析成任务或默认扩大范围。诊断记录实际返回工具数和是否要求工具，便于定位供应方执行缺口，不保存正文。

本轮附件同时接入Explain视觉输入：仅按当前actor/project/conversation/attachment_id读取私有Storage，验证路径与checksum并按既有尺寸上限缩放。附件不登记成已查看原图页，下一轮不携带原轮图；重试按同一轮附件重读。辅助图不是整页坐标证据，原提取Worker的原图定位/冻结规则/候选确认边界保持。

设计依据：[ADR-0023](../../adr/0023-independent-explain-agent.md)。

1. 已完成：在既有explain_agent目录实现行/图纸/证据契约、只读repository、四节点LangGraph及短期对话服务。
2. 已完成：可挂载鉴权HTTP/SSE、配置工厂、Prompt资源打包和CLI；验证越权/版本/缺证据/取消/失败/并发/字段差异。
3. 已完成：20项模块及共享网关/Server共59项离线回归、Ruff/9源码strict mypy通过，CLI帮助/Prompt打包检查通过；README、TODO、路线与变更记录同步。未挂前端/共享服务，未调用真实模型或数据库，真实联调待后续接入。
