# Agent 服务设计索引

ABB 独立三阶段资源演进见 [初版记录](./changelog/2026-10-12-abb-resource-draft.md)、[1.1.1 精简记录](./changelog/2026-10-12-abb-resource-compact.md) 和 [1.1.2 可用实现](./changelog/2026-10-12-abb-ready-profile.md)。当前各阶段一案例、图片 1/1/2 张；独立 `abb_native` adapter/policy 和 Bucket 可用包已完成，真实模型字段级回归仍待人工验收。

规则库人工创建/删除与动态注册见 [实施记录](../server/changelog/2026-10-12-shared-rule-library.md)：所有登录用户共享手工规则包，存储后直接可用，同 key 新任务选择最新 active 版本；停用后精确历史绑定仍可读取。AI 规则修改按 [ADR-0013](../../adr/0013-confirmed-rule-update-without-evaluation.md) 经一次用户确认后直接启用。

当前归因/确认/直接规则发布契约见 [2026-10-13 实现记录](./changelog/2026-10-13-confirmed-rules.md)。旧 [候选评测计划](./candidate-release-plan.md) 仅为历史记录；不再开放新评测任务。三阶段提取及结果校验不变。

目标评测 Stage 2 已补齐起点定位，保持正确终点隔离；旧评测产物不覆盖，失败候选的新评测入口仍是独立缺口。见 [定位修复记录](./changelog/2026-10-12-evaluation-source-locator.md)。

> 状态：Draft for review  
> 日期：2026-10-09  
> 目标部署：独立 Python 服务，默认端口 `8100`

## 结论

Agent 与业务 Server 分开部署。业务 Server 持有项目、工作区、图纸、线表、反馈和结果版本的业务事实；Agent 服务负责图纸类型识别、提取工作流、局部重提取、问题归因和 Profile 候选评测，不直接覆盖生产业务数据。

系统采用“一个对话 Supervisor + 多个专业子 Agent + 确定性工作流 + 严格工具协议”，而不是一个拥有全部权限的万能 Agent：

- Supervisor Agent：唯一用户交互入口，理解意图、请求补充信息、选择工作流并转发阶段事件；
- Profile Detection Team：判断 ZH、ABB 或 UNKNOWN；
- Extraction Team：执行 Stage 1 页面分类、Stage 2 当前页提取、Stage 3 跨页补全；
- Correction Workflow：确定性定位反馈范围，复用 Stage 2/3 执行局部重提取，不再设置独立 Remediation Agent；
- Improvement Team：归因共性问题、生成候选 Profile 变更并运行回归；
- Release Gate：确定性指标和人工审核通过后才发布新 Profile。

## Harness 建议

需要 Agent Harness，但 V1 不建议额外引入一个高层“自学习 Agent 框架”。Harness 在本项目中是一层自建的受控运行底座：

```text
Tool Registry + Model Gateway + Context Builder + Checkpoint Store
+ Trace/Event Store + Eval Runner + Profile Sandbox + Release Gate
```

LangGraph 继续负责有状态、可恢复的在线 Graph；Harness 负责工具权限、轨迹记录、离线评测和候选版本发布。用户反馈不能直接修改生产 Prompt、Few-shot、代码或校验器。

## 文档

- [混合纠错终端验收](../../../services/agent/agent_test/2.纠错agent/README.md)、[实施记录](./changelog/2026-10-11-correction-terminal-acceptance.md)：纯 HTTP 混合输入、模型输出观测、人工确认和“规则无问题／拒绝候选”第一个脚本；第二个暂不实现。

- [开发 TODO](./TODO.md)：按模块骨架、子 Agent、Graph 集成和验收门槛顺序执行的开发清单。
- [总体架构](./architecture.md)：服务边界、模块、Agent 角色、Graph 和部署。
- [Server-Agent 契约](./server-agent-contract.md)：接口、状态、事件、数据所有权和幂等。
- [反馈与自完善](./feedback-and-improvement.md)：局部重提取、问题归因、Eval Harness 和发布门禁。
- [Supervisor 与工作流](./supervisor-and-workflows.md)：对话主 Agent、意图路由、子 Agent 调度和事件反馈。
- [Supervisor 与专业 Agent 串联 V2](./supervisor-agent-orchestration-v2.md)：Profile Detection 内部工具、受控数据工具、三态跨页纠错和 Improvement 发布闭环。
- [三阶段持久化改造方案](./stage-persistence-refactor-plan.md)：V1.1 逐项提交、权威集合、Worker 接管/fencing、最终收尾、项目树发布与 Gate A/B；Gate A 机制和 Gate B 接口/Fake 验收已实施，真实模型验收待执行。
- [纠错 Agent 与 Profile 资源包改造方案](./correction-agent-refactor-plan.md)：混合纠错批次、统一 Stage 2→Stage 3、Bucket Profile 资源包、Improvement 证据和 test0 人工验收；当前为待实施方案。
- [Gate B 执行计划](./gate-b-implementation-plan.md)、[实施记录](./changelog/2026-10-11-gate-b-implementation.md)：内部业务上传/确认/Worker/SSE 与纯 HTTP 客户端。
- [ADR-0001](../../adr/0001-independent-agent-service.md)：独立 Agent 服务和受控结果提交决策。
- [ADR-0004](../../adr/0004-agent-result-persistence-boundary.md)：规范化结果落库、显式修订确认和持久化 Improvement 边界。
- [ADR-0005](../../adr/0005-retire-zh-workflow-runtime.md)：`zh_workflow` 迁移、公共文档 Graph 与 Profile 策略边界。
- [ADR-0006](../../adr/0006-supervisor-short-term-memory-and-detection-acceptance.md)：阶段 0 HTTP 验收、会话附件与 Supervisor 短期记忆。
- [ADR-0007](../../adr/0007-durable-extraction-stage-boundaries.md)：三阶段数据库持久化边界。
- [ADR-0008](../../adr/0008-gate-b-internal-business-imports.md)：Gate B 内部上传、原子入队与人工确认范围。
- [ADR-0009](../../adr/0009-profile-resource-package-storage-and-correction-batches.md)：Profile 资源包不可变存储和混合纠错批次（Proposed）。
- [ADR-0010](../../adr/0010-in-place-confirmed-corrections.md)、[实施记录](./changelog/2026-10-11-in-place-corrections.md)：用户确认后的局部修订原位更新，稳定 ID、revision、审计与幂等，覆盖此前局部修订复制整份快照的约定。
- `changelog/`：Agent 模块阶段记录。
- [混合纠错起点匹配修复](./changelog/2026-10-11-scoped-correction-source-matching-fix.md)：区分位置/设备/端子并拒绝漏修；33 项离线回归通过，用户需重载 API/Worker 后新会话重试。
- [Improvement 归因输出契约修复](./changelog/2026-10-11-improvement-diagnosis-schema-fix.md)：动态注入完整 Diagnosis Schema；修订已提交时仅重试归因，不重新注错/提交。

## V1 验收重点

1. Agent 服务可在 `8100` 独立启动、探活和测试。
2. Server 只能通过版本化内部 API 调用 Agent。
3. ZH 三阶段流程迁移后固定案例不回退。
4. Profile 识别低置信时返回 UNKNOWN，不强行提取。
5. 单条连接或工作区反馈能产生局部结果补丁和清晰 diff。
6. 自完善只生成候选 Profile；未经评测和人工审核不能上线。

## 当前实现状态

- Gate A 已实现并验证：[实施记录](./changelog/2026-10-10-gate-a-implementation.md)。正式 Supabase FULL_EXTRACTION 使用 protocol 2 的数据库阶段屏障、RUNNING 接管和幂等 finalize；10 个真实库/Fake VLM 场景分批通过。
- Gate B 的内部上传/确认/HTTP/SSE 和 `1.3stage` 纯 HTTP 验收入口已实现；真实模型人工验收仍需显式运行，Web/JWT 业务代理尚未接入。
- 阶段 0 已有纯 HTTP 终端验收脚本；独立 DETECT_PROFILE 意图调用首页识别并强制等待确认。HTTP 回合加载最近 12 轮对话、附件、待确认事项和确认结果；只实现同进程短期记忆，服务重启/多实例/长期记忆尚未支持。
- 正式 ZH 提取已迁入公共 `graphs/document_extraction`，Stage 1/2/3 子 Agent 继续负责模型调用；PDF/checkpoint/导出迁入基础设施，共享结构化阶段模型。ZH 确定性规则通过策略注入。`zh_workflow` 兼容目录已删除，全部调用直接使用新模块。
- 旧相邻页分段与批量提取及关联决策器、协议、批量 checkpoint 已删除，旧 `agent_service.zh_workflow.*` import 路径不再受支持。
- M0-M7 已完成离线实现；M8 已具备 Run/Worker、阶段 Artifact/Event、SSE、取消/恢复和 `ResultProposal`，Supabase 模式已接入持久 Run/Event/Artifact/Proposal/Checkpoint repository 与带租约的跨进程队列。完整进程中断续跑测试及 ZH 真实字段级基线仍未完成。
- M9-M10 已串联 Supervisor Graph、受控结果查询/纠错工具和三态 `is_cross_page` 路由。明确答案直接生成最小 patch；重新识别按 `same_page/cross_page/unknown` 调用 Stage 2/3；按 ADR-0010，Supabase 模式在用户确认后通过受控 RPC 原位更新当前连接，保留 ID/线号、增加 revision 并保存审计，不再复制整份 accepted 版本。
- M11-M14 已串联 accepted-feedback intake、问题归因、显式候选授权、Profile Sandbox、Eval Runner、Evaluation Judge、Release Gate、人工审批、canary、审计和回滚；反馈、候选、评测、门禁和审计 repository 已持久化。
- 纠错混合批次、Bucket Profile 资源包适配器和 Improvement 证据上下文已写入代码；26 项相关离线测试通过。本地新增 migration 和 ZH bootstrap 包已部署、下载校验通过；API/Worker 远端包开关及真实人工验收未执行，不能称完整生产验收完成。详见[部署记录](./changelog/2026-10-11-profile-package-deployment.md)。
- M15 的 ABB 执行阻塞已解除：ABB Stage 2/3 使用独立指令、图片和确定性策略，不含 ZH `XD` 白名单。真实模型字段质量尚未验收。
- M16 被跨模块基础设施阻塞：`apps/api` 尚未形成可用业务 API，Web 仍使用 Mock Supervisor，Server 会话持久化、事件代理、结果事务和生产授权适配器未实现。
- 详细代码状态、命令和限制见 [`services/agent/README.md`](../../../services/agent/README.md)，逐项验收状态见 [Agent TODO](./TODO.md)。

## 参考依据

- LangGraph 适合组合确定性步骤与模型驱动步骤，并提供持久化、流式处理和人工介入能力：[LangGraph 官方概览](https://langchain-ai.github.io/langgraph/)。
- 对固定且可分解的提取流程，优先使用工作流；只有问题归因和改进规划等开放任务才提升 Agent 自主性：[Anthropic Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)。
- 自完善应建立可复现评测，避免在生产反馈上反应式修改规则：[Anthropic Demystifying Evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)。
