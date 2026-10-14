# Supervisor 对话微调

2026-10-13，用户授权本地实施；保持现有任务、权限和提取边界。

## 设计

- Supervisor 定义为电气图纸与线表智能助手，增加 CHAT 意图；问候、闲聊、能力咨询和一般电气说明直接回答，不分派工作流。
- 任务意图仍使用结构化决策；CHAT 通过只读文字模型回复，SSE 只发送公开回答内容，不暴露模型内部推理。
- 增量消息使用既有 SSE message 帧，事件类型 ASSISTANT_DELTA；最终 ASSISTANT_MESSAGE/response 更新同一消息，避免重复卡片。非流式接口仍返回完整答案。
- 日常回复和用户消息使用对话样式；确认卡片仅用于 PDF 提取、局部重识别/修订和规则修改。任务公开说明显示完成后才显示后续卡片。
- PROCESS_DOCUMENT/DETECT_PROFILE 没有附件时只提示上传；来源必须属于当前用户会话，保留已有 PDF 类型确认、Stage 1/2、幂等与持久化边界。继承的会话 PDF 可用于明确任务指令，问候不重提取。
- 不改变业务 Server JWT、数据库 Schema、远端 Profile 或队列；SSE 仍由业务 Server 透传。公共领域 Schema checksum 同步，新意图为向后兼容枚举扩展。

## 执行顺序

1. 已完成：复现问候确认卡片及消息顺序，补测试；实现 Agent 路由/公开回复流与前端消息展示。
2. 已完成：77项离线 Agent/Server测试、Web 类型/lint/build、浏览器夹具和桌面/窄屏截图。
3. 已完成：同步 README、TODO、roadmap 和变更记录；运行服务仍需用户加载新代码，真实对话/流式提供商兼容未验收。
