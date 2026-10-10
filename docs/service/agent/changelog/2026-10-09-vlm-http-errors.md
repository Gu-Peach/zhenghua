# VLM HTTP 错误诊断

## 变更

- HTTP 错误记录状态码及 provider 返回的 `message`、`type`、`code`、`param`，文本截断并对常见密钥格式脱敏。
- 三阶段 adapter 只对响应 JSON/schema 错误重试；HTTP 请求错误直接向上传递，不再伪装为结构化输出错误。
- ZH 工作流遇到不可重试的模型请求错误（如 HTTP 400）立即终止，避免继续请求整本 PDF 后续页面。
- CLI 将 Agent 领域错误简洁输出到 stderr，并返回非零退出码。

## 验证

- 使用 MockTransport 验证 HTTP 400 保留 provider 错误详情且只发出一次请求。
- 使用 Fake Gateway 验证请求错误不会触发 schema 重试。
- 本地 Fake Stage PDF 工作流仍生成三阶段 JSON 与 XLSX。
- 未向真实模型发送额外请求；实际拒绝原因需用单页命令查看 provider 返回消息。
