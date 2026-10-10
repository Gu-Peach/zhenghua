# NInfer 图片 detail 兼容

## 变更

ZH 三阶段当前页和 Few-shot 图片请求统一使用 OpenAI-compatible `image_url.detail="auto"`，兼容 NInfer 固定 Vision frontend。此前传入 `high` 会被服务端以 HTTP 400 拒绝。

## 验证

- Native stage 测试检查 Stage 1/2/3 及 Few-shot 图片均使用 `auto`。
- 离线 PDF 到三阶段 JSON/XLSX 工作流通过。
- 未向真实模型发送请求；建议先使用 `--max-pdf-pages 1` 验证服务端。
