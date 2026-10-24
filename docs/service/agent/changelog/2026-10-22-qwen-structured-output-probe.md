# 当前 Qwen 27B 端点结构化输出探测

日期：2026-10-22。用户明确授权测试当前模型接口是否支持服务侧 Schema 约束。

## 结论

当前部署端点没有开启结构化输出。`response_format.type=json_object` 和 `json_schema` 均被 HTTP 400 拒绝；尚未进入可验证 Schema 生成约束的阶段。此结论仅针对当前访问路径及部署配置，不能推断模型权重不支持该能力，也未识别底层推理引擎。

配置模型名为 `Qwen3.8 27B`，普通请求响应声明的模型名为 `Qwen3.8-27B-Instruct`；名称来自配置和响应，并非权重鉴定。

## 方法与结果

读取 Agent 既有配置与认证信息，直接访问同一 Chat Completions 端点。仅发送合成文本，无图片、用户数据或业务工具调用。独立临时探测脚本要求同时提供 `--allow-real-model` 与 `AGENT_ALLOW_REAL_EVALUATION=true`，不纳入默认测试。

用 Pydantic 生成禁止额外字段的 Schema：`blank` 为布尔值，`marker` 为仅出现在 Schema 中的随机固定字符串，`page` 为整数且最小值、最大值均为7。三次请求使用相同提示词，要求返回与 Schema 冲突的固定 JSON；Schema 不写入提示词。temperature=0，max_tokens=512，无自动重试。

| 请求 | HTTP | 结果 | 耗时 |
| --- | --- | --- | --- |
| 普通请求，不带 response_format | 200 | 遵从提示词，返回故意不符合Schema的JSON；本地Pydantic严格校验正确拒绝 | 3.426秒 |
| response_format: json_object | 400 | response_format_not_supported | 0.036秒 |
| response_format: json_schema，strict=true | 400 | response_format_not_supported | 0.068秒 |

两次错误内容一致：

```json
{
  "error": {
    "message": "structured output requires the server to start with --structured-output",
    "type": "invalid_request_error",
    "param": "response_format",
    "code": "response_format_not_supported"
  }
}
```

成功调用报告37输入tokens、18输出tokens，总计55tokens，推理tokens为0；两次错误没有返回usage，不能认定其计费为零。未配置单价，无法计算金额。三次HTTP请求累计约3.53秒。

## 影响与后续

没有修改生产模型网关、环境配置、Prompt、Profile、数据库或Storage，也未启停服务。当前继续使用已有提示词Schema与本地Pydantic校验。

若要启用服务侧约束，需要端点维护者核对实际推理服务、启动参数及网关透传行为。错误中的`--structured-output`是当前服务自行提示的参数，不据此假定它属于某个推理引擎。启用后应重跑相同对照，确认Schema约束确实生效；本轮未做此部署操作，也未验证复杂提取Schema、多模态输入或token屏蔽的内部实现。

临时脚本及安全诊断报告位于Git忽略目录`.runtime/schema-probe/`，不提交模型运行产物，不保存API key或Authorization header。
