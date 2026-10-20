# Explain兼容决策格式失败与安全诊断

用户轮次03be5d8a-2d62-4dd1-b6bd-f127c7f9e9d2：诊断c0b392a1为0.6072秒HTTP400/tool_choice_not_supported；随后c24fb14e为5.5445秒MODEL_SCHEMA_INVALID，已切到0tools、无tool_choice、output_model结构化兼容分支。该分支已加载并运行，不能归因于仅未重启或Worker未启动。

上传附件为PDF11、969×826。只读核对实际会话 `be483d5b-4e38-4505-8f18-002f58c11005` 的任务数为0；最新此前任务来自另一会话，未作为本轮成功凭据。当前失败在模型决策/协议的本地格式校验，尚未执行重扫工具。

旧Trace只记录unknown，没有原模型输出或底层validation_errors，因此不能从现有证据断言具体缺哪个字段、非JSON、错误action标签还是意外工具格式。不能据此诊断输入超限、图像丢失或已进入提取。此轮图片/请求规模已记录，未代调用真实模型重现。

补充 `diagnostics.py`：MODEL_SCHEMA_INVALID稳定分类schema_validation；只记录校验项数量、最多12个错误类型及每项最多12段字段路径。路径名和分支标签必须来自本地Pydantic Schema；未知/模型自造字段替换为`<field>`，数组位置只允许有限非负整数，错误类型使用白名单。控制台和本地Trace同样脱敏，不保存模型原文、异常input/context、字段值或第三方错误消息。无output_model或意外协议错误无法提供路径时保留0项，不编造原因。

5项回归先复现诊断缺失；76项诊断/兼容/回执离线测试通过，覆盖无效JSON、缺字段、错误标签、额外敏感字段、计数/路径上限，以及原兼容降级和入队门禁。Ruff和修改源码严格mypy通过。未运行浏览器、全仓或真实模型测试；无HTTP DTO、Schema、Profile、数据库或Web变化，无迁移。

本轮不放宽校验、不自动重试Schema错误、不创建任务或改正式线表、不启停服务。重载8100后未来失败会输出具体安全校验路径，旧诊断文件不会被补写成已知原因；本次并未证实模型输出问题已修复。无需重载8000或Worker。设计见[说明](../explain-schema-diagnostics.md)。
