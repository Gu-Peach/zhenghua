# 案例 A：确认后归因启动 409 修复

日期：2026-10-11。用户确认 `b7b13a2d-283a-4e7e-98f5-fb4f227af6a2:result-proposal` 后返回 HTTP 502，内部为 Supabase HTTP 409。

## 实际状态与原因

只读核对确认业务结果已经提交：

- test0 结果版本 2 为 `accepted`，ID `c31c5402-e505-4a9e-a4dc-f24450e01d71`。
- 新连接 `bd4bce43-083a-4597-a6dd-590c4e7d2a5c` 的终点端子为 `2`；旧版本连接仍保留 `999`。
- feedback `9221c12b-b5a2-5db5-b195-2d8ab8146e86` 已 accepted。
- 没有成功创建相应 Improvement run。

错误发生在提交后的异步归因启动。`CorrectionWorkflowHandler` 把 `feedback.feedback_id` 填入 `CreateRunRequest.source_document_id`，而该列必须通过 `(source_document_id, project_id)` 外键引用真实的 `document_files`。真实来源 PDF ID 为原 correction run 的 `73d72bce-f0a6-53f5-a34c-438f01325d9f`，不能用反馈 ID 替代。

## 修改

- 提交前读取 proposal 的原 correction run，校验项目一致。
- 创建 Improvement run 时复用原 correction run 的 source document；feedback ID 仍写 `feedback_id`，不混用。
- 给 Improvement run 明确绑定 accepted feedback 的 frozen ProfileRef。
- 结果提交后若归因创建发生受控错误，返回 `COMPLETED` receipt，包含 `correction_committed=true`、已提交结果版本、`improvement_status=START_FAILED` 和安全错误码。不会把已提交修订返回为失败，也不会因为归因错误回滚修订。
- 同 proposal 的确认可通过现有 `source_proposal_id` 唯一 receipt 幂等复用结果版本，并使用固定 Improvement 幂等键补启动。更广泛的协议 1 队列接管/跨事务恢复仍是已有待办，不在本次修复中宣称完成。

## 验证与下一步

先增加真实串联回归，断言 Improvement source_document_id 等于原 PDF，而非 feedback；旧实现复现失败。另补“归因启动失败但修订成功”的回归。5 项相关测试、修改文件 Ruff 和全包 strict mypy 通过。

本轮没有再调用确认接口、创建归因 run、再次写结果、修改模型/Profile、数据库结构或重启服务。用户重载 Agent 后，可重发同一确认请求：应复用版本 2 并补启动归因，不需要重新注错，也不应创建版本 3。
