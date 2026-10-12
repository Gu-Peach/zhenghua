# 补丁文件内嵌代码块的 JSON 解析修复

## 根因

恢复后的 ProfilePatchBuilder 再次报 invalid_json。最新持久 Trace 的 response_content 可直接通过 ProfilePatchModelOutput.model_validate_json：输出是合法 JSON，包含两个 replace operation。问题在公共 Gateway：re.search 在整个响应中先寻找 Markdown fence，将 JSON content 字符串中的 Prompt 示例代码块误截为外层响应。

Trace 不保存请求 messages，因此不能据此证明服务有没有加载新的 system Prompt；本次不再把失败归因为旧服务。实际证据证明的是解析器缺陷。

## 修复

model_gateway._load_json 先 json.loads 完整响应；失败后仅通过 fullmatch 识别整个响应的外层 fence，再保留既有 JSON 片段兼容解析。字符串里的反引号和 JSON 示例不应改变外层结构。严格 Pydantic 校验、错误分类、暂时性重试和发布门禁不变。

新增回归覆盖嵌套文件内容：纯 JSON、外层 json fence、带前言三种情况；验证 operation 和中文/换行完整保真，保留无效 JSON/字段拒绝测试。

## 验证

31 项 Patch/Gateway/Harness/Diagnosis/Supervisor 离线测试通过；158 个 Agent 源码 strict mypy 与修改文件 Ruff 通过。最新失败 Trace 使用修复后的解析器只读重放通过，两份 content 具有真实换行（无双重转义）。没有模型调用、数据库写入、任务恢复、规则包发布或服务重启。

需用户重载 API/Worker 后再 resume 同一失败 Improvement run，不能重新注错/提交已完成数据修订。此次不声称候选评测或生产发布已完成。
