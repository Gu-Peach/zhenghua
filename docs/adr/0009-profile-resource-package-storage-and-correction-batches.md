# ADR-0009：Profile 资源包存储与混合纠错批次

- 状态：Proposed
- 日期：2026-10-11
- 关联方案：[纠错 Agent 与 Profile 资源包改造方案](../service/agent/correction-agent-refactor-plan.md)

## 背景

纠错链路需要重新读取当次提取使用的 Prompt、Few-shot、expected JSON、规则和 Schema，才能判断问题来自模型感知还是 Profile 规则。当前 Profile 主要从本地目录加载，Improvement 上下文也不能稳定拿到完整阶段证据。一条用户消息还可能同时包含明确答案、同页重识别和跨页重识别，单一 `target_hint` 无法表达这种混合任务。

## 决策

1. 将每个 Profile 的 Prompt、Few-shot、expected JSON、规则和校验配置打包上传到私有 `agent-profile-assets` Bucket；包按 `profile_key/version` 不可变保存，并由 manifest 和 sha256 checksum 校验。
2. 新增资源包元数据表（实施时通过 migration 创建），保存状态、对象路径、checksum、派生关系和审核发布审计。生产结果只绑定资源包版本，不复制 Prompt 正文到结果表。
3. Supervisor 将自然语言纠错转换为 `CorrectionBatch`，确定性拆分为 direct patch、Stage 2、Stage 2→Stage 3 三类。跨页重识别永远走 Stage 2 → Build Tasks → Stage 3，不提供 Stage 3-only 路径。
4. Stage 2/3 和 Improvement 通过统一 ProfilePackageRepository 按 frozen version/checksum 加载资源包；前端仅通过业务 API 获取元数据和签名 URL。
5. 用户确认规则建议只授权创建候选资源包。候选仍需固定回归、评测、人工审核、canary 和发布门禁，不自动修改 active 包。
6. 纠错验收复用 test0：在隔离结果版本人工注入错误，标记 `manual_injected_test_error`，通过已有 Supervisor HTTP 对话手工输入；不新增专用终端脚本。

## 取舍

- Bucket 保存大对象和完整资源，数据库保存可查询元数据，兼顾前端展示、审计和可复现性。
- 串行单 PDF 处理降低调度复杂度，但仍保留版本、checksum、幂等和历史绑定，避免未来多 Worker 或恢复时结果漂移。
- 人工注错能验证纠错决策和持久化闭环，但不能单独证明幻觉或规则缺陷，因此诊断必须携带错误来源并展示证据限制。

## 后果

- 需要新增 Bucket、资源包元数据 migration、上传/下载/签名 URL 适配器和本地缓存校验。
- 现有 Profile Registry 需要保留本地开发兼容模式，同时增加生产 frozen package 加载路径。
- 混合批次必须在 Supervisor、Correction Workflow、API DTO、事件和幂等键中保持一致。
- 历史项目继续绑定旧 Profile 版本；发布新包不会重写历史结果。

## 不在本 ADR 内

- 不改变三阶段业务表和最终线表字段。
- 不引入 Stage 3-only 流程。
- 不实现本轮代码、数据库 migration 或资源包上传；这些在用户确认方案后按改造计划分阶段实施。

