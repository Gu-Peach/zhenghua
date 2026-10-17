# Explain Agent：行/页检索工具

2026-10-16。设计：[ADR-0024](../../../adr/0024-explain-retrieval-tools.md)，当前入口：[模块README](../../../../services/agent/src/agent/explain_agent/README.md)。

## 交付

原来固定查一行后回答，现在前端可传connection_id或ConnectionQuery。查询支持来源/目标业务页、PDF物理页、原理号、线号、起/终点端子、工作区和行ID的精确AND匹配。保留旧行请求及context.row契约；query入口context为SearchResult。项目/身份/批次由程序绑定，模型不能指定其他项目、用户、SQL或路径。

LangGraph增加模型→工具→模型条件循环。search_connections按稳定顺序分页，返回行、原页、所有已确认目标页、唯一匹配的引用候选图及已保存提取依据；按物理页聚合图纸关联。模型可继续检索其他行/页与后续分页。coverage报告实际取回范围；提前结束和每轮8次调用上限都不冒充完整覆盖。

view_drawings按需读取已检索图纸，私有Storage权限/路径校验后下载并转内联图像；每次最多4页，每轮6页，每图最多100万像素/1536px长边。界面仍拿到原图300秒签名地址，签名和路径不进入模型。visual_pages说明实际提供的图像；看图与历史提取过程分别解释，不重新提取或写库。

每轮刷新初始上下文、历史查询及图片摘要，变动使聊天历史/缓存失效。重复turn也重查权限与检索；保留取消、并发和有界短期会话。共享ModelGateway仅增加可选tools/tool_calls并解析流式工具分片，旧调用不发送工具字段。

可挂载HTTP/SSE同步Pydantic/OpenAPI契约，SSE公开context/retrieval/answer_delta/completed；内部state、工具原始参数和图像base64不流给界面。CLI新增页/端子筛选。尚未挂载到8000/8100或前端聊天按钮，不新增服务。

## 验证

- Explain相关三份测试文件共51项通过。连同共享网关/Harness、模型Trace及Server默认回归共94项通过；全部FakeModelGateway/MockTransport/TestClient。
- 修改源码/测试Ruff通过；12份Explain源码及共享网关共13份源码strict mypy通过；CLI帮助、OpenAPI查询/响应Schema和文档链接检查通过。
- 额外检查旧test_supervisor_chat.py时，有2项在读取已不存在的services/agent/prompts/supervisor.md时失败，发生在模型调用前；本次不修改旧Supervisor或恢复历史Prompt。其余旧聊天/流式网关用例通过。
- 未调用真实数据库、Storage或付费模型，未提交数据库数据、改提取规则、迁移表、重启服务或实施旧Agent清理。真实提供商工具/视觉兼容、真实权限及前端交互仍待接入后联调。
