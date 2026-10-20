# Explain 补调未执行与聊天图片

后续现场已确认当前服务拒绝required工具选择，已增加精确错误触发的结构化决策兼容，见[后续修订](./2026-10-20-explain-tool-choice-compatibility.md)。以下保留本轮历史交付与当时验证边界。

## 现场核实

北京时间12:01，同一轮首答与补调均正常stop，`tool_result_messages=0`、`prior_tool_names=[]`、`image_count=0`。首答约74020文本字符，补调约74462字符。前一轮修复阻断假成功，但补调仍只靠文字要求调用工具；本轮没有实际执行。只读查询确认10月20日仍无新重扫任务，不能归因为Worker排队。

旧组件立即上传图片并长期持有ID，后续消息会重复携带。Explain之前只有附件ID，图像仅由重扫Worker读取，Explain自身没有收到图片。

## 修订

- ModelRequest新增可选tool_choice，同步发送到流式/非流式供应方请求，默认不发送。仅缺回执重扫补调及随后尚无回执的检索轮要求required，仍只开放原有受控工具。
- 补调采用当前结构化行、选择、图纸索引、分页覆盖与最新需求，不重发原始提取产物或无回执答复；保留本轮已读图像。没有把正文解析为任务或推测行ID/扩大范围。
- “终点在本页”使用fields=end，并将已取得行ID绑定其source_drawing_page；不照抄旧跨页目标，不把用户预期端子当识别结果。
- 私有附件校验actor/project/conversation/id、固定路径、uploaded状态和SHA-256，经既有缩放后进入首答/补调视觉输入。绑定PDF上下文不代表实际图片页号或整页坐标；附件不计入visual_pages，下一轮不自动加载，原轮重试按ID重读。
- 诊断增加tool_choice与returned_tool_calls计数，不保存正文/图像。供应方不返回工具时明确“模型未返回重扫工具调用”，任务未创建、正式线表不变。

HTTP DTO、OpenAPI、数据库、Worker和候选确认契约保持，无迁移。UI见[Web交付](../../../apps/web/changelog/2026-10-20-explain-chat-images.md)。

## 验收与启用

155项Explain/网关/Harness离线测试通过，最终47项复验通过，Ruff和5源码strict mypy（--follow-imports=silent）通过。覆盖required真实HTTP请求体、检索后继续调用、供应方忽略工具、图片跨轮隔离、外用户/项目/会话/路径拒绝及摘要校验。附件测试初次6项失败为夹具将签名POST误计成下载，修正GET计数后通过，未放宽生产权限。

本轮仅只读现场，无真实模型、任务创建、正式线表修改或用户服务启停；数据库写入集成未运行。尚未验证当前供应方required支持及真实识别质量，不能宣称真实重提取已通过。

重载8100、刷新Web重开窗口后重新发送。无需重载8000/Worker或修改启动命令；原失败轮没有真实任务可恢复。
