# Agent 服务设计索引

- [独立Profile Agent交付](./changelog/2026-10-17-profile-agent.md)、[模块入口](../../../services/agent/src/agent/profile_agent/README.md)、[ADR 0026](../../adr/0026-independent-profile-agent.md)：模板填充、诊断、受控草稿编辑和包输出，界面/正式发布后接。

- [Explain共享宿主与公开工具事件](./changelog/2026-10-17-explain-host.md)：工具状态/结果SSE、8000→8100可信身份和独立前端浮窗接入，启动需加载src.extraction_main。

2026-10-16新增ZH列区域裁剪实验：显式`--profile zh_crop`启用，`zh`保持整页；初扫不改。2026-10-17用户确认本版可一起提交，已解除源码及配套测试/文档的本地忽略与提交保护，运行产物仍忽略，不代表生产规则发布。设计与核对见[实验方案](./zh-completion-crop-plan.md)。

- [Explain检索工具](./changelog/2026-10-16-explain-retrieval.md)：行/页精确查询、跨页图纸、分页覆盖及按需视觉分析，LangGraph原生工具循环；51项Explain/共94项相关离线测试通过，前端/共享服务仍未接入。设计见[ADR-0024](../../adr/0024-explain-retrieval-tools.md)。

- [独立Explain Agent](./changelog/2026-10-16-explain-agent.md)：三表行级来源解释、图纸证据、短期多轮与可挂载HTTP/SSE；20项模块、59项组合离线验证，尚未接前端或共享服务。设计见[ADR-0023](../../adr/0023-independent-explain-agent.md)。

- [上传提取、增量发布及复核后处理](./changelog/2026-10-16-incremental-extraction.md)；[ADR 0022](../../adr/0022-incremental-extraction.md)。

2026-10-16按用户精简后的manifest保留003C01的1组初扫、5组补全/负例和4张图，删除独占未引用6图/12JSON；manifest v13、资源摘要与测试引用同步，Profile保持2.1.1。仅静态核对，未运行测试/模型。见[清理记录](./changelog/2026-10-16-zh-c01-example-cleanup.md)。

2026-10-16本地ZH2.1.1修正003.C/004.C跨页读取：上下文v2移除起点端子/坐标/方向文字，允许页底朝外回指，接口/针脚分别读取，缺失地址只用唯一来源页PDF证据核对。5初扫/9补全/10图，补全仍每次1例；仅静态核对。见[方案](./zh-cross-page-reading-fix-plan.md)与[记录](./changelog/2026-10-16-zh-cross-page-reading.md)。

2026-10-15本地ZH2.1.0定向补全改为只发送目标图和初扫来源事实，扫描增加可见signal_name，ABB/XMZ保持双图。资源/Schema/语法/类型与CLI静态核对，未运行测试或模型。见[设计](./zh-target-only-completion-plan.md)与[记录](./changelog/2026-10-15-zh-target-only-completion.md)。

2026-10-15按用户要求优先保留实际输入图像素，再压缩/整组减少Few-shot；输入自身超预算才缩小，尺寸/删例metadata和缓存指纹同步。仅静态核对，未运行模型/测试。见[记录](./changelog/2026-10-15-input-first-image-budget.md)。

2026-10-15所有模板主表统一ZH14列，共用表头/行映射/默认样式；ABB1.1.4/XMZ0.1.2补齐实际端子坐标Prompt与图像expected。仅静态核对，不跑测试/模型或覆盖旧结果。见[交付记录](./changelog/2026-10-15-unified-table-coordinates.md)与[ADR-0019](../../adr/0019-unified-extraction-table.md)。

2026-10-15通用JSON Schema注入与ZH专属约束解耦，ABB收到完整字段契约；本地PDF入口保存原始模型响应、finish_reason和用量，明确length时不当普通JSON语法错误重试。仅静态检查无新增lint，未运行测试/模型或写库。见[修订记录](./abb-output-contract-fix.md)。

2026-10-15公共提取请求补齐实际图最长边2048px与案例/实际图总计600万像素限制，保留原图和归一化坐标，metadata记录发送尺寸；仅静态检查，无新增lint，未运行测试/模型或写库。见[设计/交付](./model-image-budget-plan.md)。

2026-10-15 ABB本地1.1.3纠正小圆圈放线/大圆圈端子、同段双标记只记一条，原理号数字或完整端子直接拼来源Sheet；Prompt/适配器/expected同步，未运行测试或模型。见[修订记录](./abb-circle-rule-update.md)。

2026-10-15本地PDF/拆页测试入口支持--profile/--model切换规则与模型，强制内存模式；操作命令见[测试说明](./local-stage2-group-test.md)，静态验证与限制见[记录](./changelog/2026-10-15-local-profile-cli.md)。

2026-10-15补齐003C01中间FC12组到003C31的双图Few-shot，manifest v10，5初扫/3补全/8图；仅静态核对。见[记录](./changelog/2026-10-15-zh-c01-middle-completion.md)。

2026-10-15本地ZH2.0.5允许端点冻结后沿对应相线读取Ie明确电流，003C01样例按实际FC11/12的160A、FC13的80A同步；未运行测试/模型或写库。见[记录](./changelog/2026-10-15-zh-ie-current.md)。

2026-10-15本地ZH2.0.4替换003C01初扫/跨页样例、清理独占旧图，并贯通起终点端子图片坐标及本地14列XLSX；仅静态核对，未运行模型/测试。见[记录](./changelog/2026-10-15-zh-c01-terminal-coordinates.md)。

2026-10-14本地ZH2.0.3元件标识优先级与样例同步，内部补全可按图像依据完善来源元件元数据，冻结端子/原理号；仅静态核对，待用户实际复测。见[记录](./changelog/2026-10-14-zh-component-priority.md)。

2026-10-14按用户确认对齐XMZ本地规则：Profile资源改用prompts/xmz，放线标记/最近端子边界、程序端子排及仅图像事实expected同步，本地0.1.1；未运行测试/模型，不写库或发布。见[记录](./changelog/2026-10-14-xmz-image-only.md)。

2026-10-14本地ZH测试脚本隔离无关模板资源错误并显示具体失败原因，ZH绑定只读检查通过，未运行提取或真实模型。见[记录](./changelog/2026-10-14-local-profile-isolation.md)。

2026-10-14按用户确认明确ZH初扫顺序：先定位放线斜杠，再沿两侧找端子/跨页箭头，最后按同段箭头定向；Prompt、调用指令和规则同步。未运行测试/模型，不写库，效果待用户复测。见[记录](./changelog/2026-10-14-zh-marker-first.md)。

2026-10-14用户移动拆分页后，本地Stage2脚本默认输入改docs/test/pages，索引改docs/test/pages/agent/drawing_index.json；未执行测试或模型。见[路径更新记录](./changelog/2026-10-14-local-pages-path.md)。

2026-10-14独立提取代码迁至services/agent/src/agent/extraction_agent，共享源包按用户布局改为src。61份源码仅移动/改引用，254份Python静态比对无非引用实现差异；Prompt/expected字节保持，不跑业务测试/模型。见[迁移记录](./changelog/2026-10-14-extraction-agent-directory.md)与[模块入口](../../../services/agent/src/agent/extraction_agent/README.md)。

2026-10-14 ZH运行时expected字段与新Prompt同步：C01完整端子、C02可见描述、FO2设备/排号区分；manifest v6/checksum同步，未运行测试或模型。见[记录](./changelog/2026-10-14-zh-expected-alignment.md)。

2026-10-14按用户要求移除ZH离线regression_cases及对应样例/独占图片，manifest v5与引用同步；运行时保留5组初扫和2组内部补全，未运行测试或模型。见[清理记录](./changelog/2026-10-14-zh-example-cleanup.md)。

2026-10-14本地ZH2.0.2按用户新口径修改：按放线段读取两侧直接端子，X/XD数字继承排号，业务端子排仅程序映射；Prompt精简，电流约束保留，M23八条用户确认样例加入。用户自行测试，本轮没有运行测试或模型；见[记录](./changelog/2026-10-14-zh-direct-terminals.md)与[ADR-0016](../../adr/0016-zh-direct-terminal-segments.md)。

2026-10-13 Supervisor日常对话完成：CHAT公开回答流、无PDF不分派提取、问候不确认既有任务；契约6、77项Agent/Server离线验证和21项浏览器夹具。设计与边界见[计划](./supervisor-chat-plan.md)，验证和服务加载限制见[交付](./changelog/2026-10-13-supervisor-chat.md)。

2026-10-13 ZH本地2.0.1质量修正：方向缺失降级、真实针脚与地址区分、原始引用解析及分支去重；40项离线冒烟与7项接口/兼容边界回归，未重跑真实模型或写库。旧121条结果保留，准确率未复验；见[记录](./changelog/2026-10-13-zh-stage2-quality.md)。

2026-10-13 本地新增大车卷盘 `zh_gantry_reel@0.1.0` experimental 资源：SH.NO. 网格页标/引用，分类、初扫、内部补全各两组实际图片；仅离线资源/接口回归，不上传、不调用真实模型。资料差异与范围见 [核对说明](./zh-gantry-reel-review.md)，规范索引设计见 [ADR-0015](../../adr/0015-zh-gantry-reel-profile.md)。

本地 002.C/002.M 测试脚本与真实执行完成：内存运行、12 页/121 条、12 列 XLSX 色标留空；14 项离线冒烟通过，31 条待复核，不写数据库/上传对象。见 [说明](./local-stage2-group-test.md) 和 [执行记录](./changelog/2026-10-13-local-stage2-groups.md)。

2026-10-13 分支提取改造：Stage 2 逐页 LangGraph 内部扫描/双图补全/保存，独立 Stage 3 Agent/Graph 删除；ZH 2.0.0 放线标记与箭头规则替代端子白名单。10 项离线冒烟通过，真实数据库/模型/远端发布未执行。新入口及兼容边界见 [交付记录](./changelog/2026-10-13-stage2-page-workflow.md) 与 [ADR-0014](../../adr/0014-stage2-page-extraction-workflow.md)。下文旧三阶段记录保留为历史基线。

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
