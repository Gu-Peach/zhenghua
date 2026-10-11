# ADR-0008：Gate B 内部上传与确认边界

日期：2026-10-11。状态：accepted（授权实施；Fake HTTP/本地 Supabase 验证通过，真实模型人工验收待执行）。

## 决策

为 Agent 阶段验收增加内部 `/v1/imports` 和 owner-scoped 项目树/结果、run 阶段摘要读接口。内部 Bearer 是可信调用者身份，user_id 是该调用者传入的已有 Auth 用户 UUID，不等于浏览器 JWT。仅允许 owner，成员授权后续由业务 API 实现；禁止把内部服务直接公开给浏览器。

上传按 owner+Idempotency-Key 固定项目/源文档 UUID。先以数据库唯一键保留 checksum，再不可覆盖地上传私有 Storage，上传响应丢失时下载校验；数据库/Storage 非统一事务。部分上传保留 reservation，原 key 重试补齐，不发布完成事件；孤儿保留/清理仍须单独策略。不创建 Auth 用户、不覆盖其他源 PDF。验收使用受限 raw PDF 上传，不替代产品大文件直传会话。

Supervisor 仍通过正常意图 Graph 判断 PROCESS_DOCUMENT/CONFIRM_INPUT。检测强制人工确认，UNKNOWN 必须明确类型；experimental 不允许进入完整提取。确认固定 Profile key/version/checksum、操作者、PDF checksum、检测 ID/置信度与确认时间。新业务导入不得继承另一个临时附件的确认。profile/version 进入 Run，确认审计进入 options JSONB；Worker 校验源文件和确认，Gate A 冻结 StageInput。

新 protocol 2 FULL_EXTRACTION 的创建、RUN_CREATED 和入队改为同一事务 RPC，以项目锁串行化幂等 key；入队失败整体回滚。RPC 仅 service_role 可执行，旧协议保持不变。不增加业务表、不修改 Gate A 完成语义。

每个业务 import 的完整提取使用固定 `full-extraction:<source_document_id>` key；短期会话丢失后重新检测/确认同一 import，只复用同版本 Profile 的既有任务，不修改原确认审计、不重新入队。想重新处理必须新建 import/key（或通过既有受控业务 run 接口明确新版本），不同 Profile 的同 key 请求拒绝。

会话仅进程内短期记忆；已经入队的 run、阶段和结果独立持久。服务重启后可按 run ID 重新查询/监听，无需复原聊天记忆；未确认会话重启需重新检测和确认。SSE 可按 Last-Event-ID 续传，关闭前排空终态事件。项目树只读 published 分类 snapshot；分页结果锁定同一 result version。

真实模型仍需显式验收命令/开关与人工输入，Fake 回归不等于真实字段准确率通过。Gate B 接口实现、Fake 验收、真实模型验收分别记状态。见 [执行计划](../service/agent/gate-b-implementation-plan.md)。
