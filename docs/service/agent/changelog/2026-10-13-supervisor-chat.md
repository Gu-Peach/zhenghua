# 2026-10-13：Supervisor 日常对话与公开回答流

## 行为

- 定义为电气图纸与线表智能助手，CHAT/未知意图安全回到对话，不分派业务任务；问候、能力咨询和一般知识直接回答。
- 保留结构化意图判断；CHAT 追加一次无工具的文字回复模型调用，使用最近24条短期对话作上下文。流式接口累积公开回答，非流式接口返回完整回答；日常聊天不确认已有PDF或恢复待处理任务。
- PROCESS_DOCUMENT/DETECT_PROFILE 没有实际附件时只提示上传。已有附件仍受会话/用户权限限制，业务提取保留类型确认及Stage 1/2。纠错、结果修改、规则发布仍经原授权/版本边界执行。
- 增加SSE message事件ASSISTANT_DELTA，最终ASSISTANT_MESSAGE/response完成同一条回复；原响应字段、业务Server JWT和SSE透传不变。公共领域契约升为6并更新checksum；Server OpenAPI重新导出无差异。
- Gateway只发送delta.content，不暴露reasoning_content或tool_calls；临时错误仅在未发送回答前重试，输出部分文字后中断不重放。取消会关闭请求。

## 修改位置

`prompts/supervisor.md`、`agents/supervisor.py`、`graphs/supervisor/graph.py`、`harness/model_gateway.py`、领域枚举/契约和前端SSE适配。

## 验证

- 77项Agent/Server离线测试通过，覆盖日常CHAT、无PDF、已有待确认PDF的问候、SSE最终回复及幂等、HTTP403不重试/503有限重试、部分回答中断、原上传确认和Fake Worker、鉴权/接口边界。
- 三个改动Agent源码文件strict mypy和修改文件Ruff通过；公共Schema snapshot通过。
- Web浏览器夹具验证见[Web记录](../../../apps/web/changelog/2026-10-13-supervisor-chat.md)。本轮修正两条旧测试的过时预期：固定ZH1.0.0查询改为已登记版本，逐页补全顺序改为scan→cross→下一页scan。
- 未调用真实模型、连接业务数据库、部署migration、发布远端规则或重启已有Agent服务。真实提供商流式兼容与实际对话质量未验收；服务需用户加载新代码。
