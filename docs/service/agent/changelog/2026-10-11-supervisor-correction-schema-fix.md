# 案例 A：Supervisor MODEL_SCHEMA_INVALID 修复

日期：2026-10-11。用户在 Swagger 提交自然语言纠错时返回 HTTP 502 / MODEL_SCHEMA_INVALID。

## 原因与修复

一次只读模型复现确认输出含 `query.workspace_page: 50` 和 `query.start_terminal: "XD3:251"`。原查询模型要求字符串页码，且只定义不区分方向的 `terminal`，因此还未进入纠错工作流就被 Pydantic 拒绝。

- `ConnectionSearchQuery` 新增可选 `start_terminal/end_terminal`，Supabase 与内存 repository 都按明确方向精确匹配；原 `terminal` 两端匹配保持兼容。
- 对 `workspace_page/wire_number` 接受模型输出的整数并转换为字符串；原字符串保持原样，前导零不会被剥离；UUID、权限、字段白名单和业务校验没有放宽。
- SupervisorTargetHint、旧单项 handler 和缺失目标判断同步支持新查询字段。
- Supervisor system 消息附加由 `SupervisorModelOutput.model_json_schema()` 生成的完整 Schema；Prompt 增加完整案例 A 输出及字符串编号约束。
- Model Gateway 的结构化校验失败保留原响应和安全字段错误到私有 Trace。Supervisor HTTP 只返回 schema、location 和 type，不返回原始模型内容或校验 input。仍不启用 provider response_format。

## 验证和边界

- 先以真实输出结构补回归，复现原始失败；修复后 23 项 Supervisor/Gateway/Harness/串联离线测试通过，strict mypy 和修改文件 Ruff 通过。
- 两次独立真实模型调用分别用于复现与修复后验证，未运行全量/长时模型评测。第二次 `decide()` 通过结构校验，生成 CORRECT_RESULT 决策，随后只读检索到一条匹配连接。
- 没有调用 Workflow.dispatch、prepare/commit 或 Stage 2/3；没有修改用户的注错数据、创建 proposal、提交结果版本、变更生产 Profile 或重启现有服务。
- 需要用户重载 Agent API/Worker，再从 Swagger 重发原请求。数据库无 Schema 变更，不需要新 migration，也无需重新上传 ZH 资源包。
