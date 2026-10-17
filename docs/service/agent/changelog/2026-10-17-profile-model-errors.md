# 第二阶段失败提示与模型诊断

2026-10-17。用户反馈第二阶段反复失败，前端只显示“规则助手模型请求失败”，后台没有异常。

只读检查当前草稿确认分类已保存、人工上传图片存在，未保存第二阶段候选。原`public_error()`把模型网关所有异常转换成同一句话；SSE在HTTP200连接中发送error且没有终端日志，真实Profile gateway也未配置TraceStore。历史失败响应未留存，无法从此次快照确认是HTTP拒绝、超时、输出截断还是外层JSON校验错误，不能将某一原因写成已证实根因。

已实施：

- 增加`diagnostics.py`，对真实Profile gateway启用既有LocalModelTraceStore，响应诊断默认写入`.runtime/profile-agent/model-traces`，失败终端日志包含阶段、错误码、HTTP状态或校验位置、诊断编号。
- 将HTTP权限/限流/服务故障、超时、JSON Schema错误和finish_reason=length截断区分。前端显示code和诊断编号，保留同轮重试能力。HTTP200仍表示SSE连接成功，error事件不代表提取成功。
- 对私有日志只保存模型公开content、finish_reason/用量/Schema信息及受控metadata，不保存请求消息、图片Base64、Authorization或API key；失败摘要不复制provider错误原文。诊断写入失败不替代原模型错误。
- 补全Wizard生成结果最外层GeneratedAnswer的完整Schema，保留内部阶段Schema及严格校验；不放宽错误字段或编造默认端点。
- Profile调用现在传递现有thinking/JSON配置；JSON模式只默认应用到结构化请求，不影响普通工具对话。当前用户配置没有显式thinking开关，不据此推定为这次失败原因，也未修改模型配置或输出上限。

验证：9项新诊断测试覆盖Mock HTTP400/403/413/429/503、外层Schema错误、截断、超时、诊断磁盘失败及配置传递；与现有Profile对话/向导/API回归通过。10项规则聊天浏览器回归及错误提示桌面/窄屏专项通过，类型/Ruff/lint/build通过。没有调用付费模型、修改实际草稿/业务数据库或启停用户服务。

运行操作：由用户重载8100 Agent，保留当前界面点击“重试本轮”，通过新错误码/诊断编号确认实际触发条件。第一阶段无需重做；如果刷新导致本轮内存状态丢失，可恢复草稿并重新发送第二阶段图片。真实模型成功验收及此次实际触发根因仍待这次复试。
