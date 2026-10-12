# 开发路线

> 最后更新：2026-10-12
> 状态含义：`planned`、`in progress`、`blocked`、`done`

2026-10-13 展示更新：图纸库改为项目→工作区→图片原地展开和预览；真实工作台采用左侧导航+中间内容，聊天为右下角按钮切换的悬浮窗口。13 项浏览器夹具及前端检查通过，见 [前端交付](./apps/web/changelog/2026-10-13-directory-floating-chat.md)。

同日工作台精简已完成：导航显示项目名称、删除重复概览、端子新增为最右加号、移除全部工作区按钮、左侧项目可折叠且去掉 PDF 中间节点、聊天去掉当前阶段卡片。13 项浏览器回归和前端检查通过，见 [精简交付](./apps/web/changelog/2026-10-13-workbench-cleanup.md)。

同日导航/搜索居中与表格内编辑已完成：保存沿用既有版本锁/审计/幂等，后台刷新不替换编辑基线，失败草稿可重试或取消。16 项浏览器回归与前端检查通过，见 [原位编辑交付](./apps/web/changelog/2026-10-13-centered-inline-edit.md)。

## Phase 0：基线与规范

状态：in progress

- [x] 整理产品需求与目标架构。
- [x] 建立文档索引、CHANGELOG、TODO 和 `AGENTS.md`。
- [x] 恢复正常本地 Git 仓库及原远程关联，补齐运行产物忽略规则和 Agent Few-shot 图片跟踪规则；业务阶段状态保持不变。
- [ ] 固化 ZH 当前案例的结果基线、耗时和费用基线。
  - 独立审校脚本已修复未知跨页页码与循环引用的待复核处理，11 项离线回归通过；真实模型审校及人工质量基线仍未完成。
- [ ] 固化 ABB 的分类、页扫描和跨页 Few-shot 回归集。
- [ ] 为现有 API 导出 OpenAPI 快照。

退出条件：需求、数据模型、迁移策略和当前质量基线可复核。

## Phase 1：Monorepo 与 Vite 壳层

状态：in progress

- [x] 创建 `apps/web`、`apps/api`、`services/agent`、`services/server` 基础边界。
- [ ] 配置 pnpm workspace、Turbo、TypeScript、Python `pyproject.toml`。
- [x] 配置 pnpm workspace、Vite 和 TypeScript strict mode。
- [x] 建立 React Router 静态登录页和应用布局。
- [x] 接入真实 Supabase Auth、HttpOnly 续期与受保护路由；一次性真实账号/API/浏览器登录通过。
- [x] 实现 Header、三栏工作台和初始静态 AI 会话原型。
- [x] 完成交互 Mock 工作台：图纸库/规则库、跨页端子定位、自然语言修复与显式模拟开关；无触发时为空态，PDF 上传后按 Stage 1/2/3 顺序流式展示 Agent 状态，Stage 1 完成后才呈现工作区和拆分页（真实 API、鉴权和持久化 SSE 待后续阶段）。
- [x] 真实工作台资源目录：图纸库按当前项目→工作区→图片原地展开和预览；规则库向所有已登录用户共享每个 key 的最新可用手工规则包，不设置草稿状态。Improvement 隔离候选仍保留原审核边界。
  - Web typecheck/lint/build、11 项 HTTP fixture 浏览器回归及桌面/窄屏截图检查通过，覆盖空目录、跨工作区点击定位和旧 draft 响应兼容显示。
- [x] 保留旧 Vite 前端作为迁移期 fallback。

退出条件：用户可登录并进入空项目工作台；CI 可构建 Web 和 Python 包。

## Phase 2：项目领域与数据库

状态：in progress

- [x] 已编写并应用本地 Supabase 的 projects/project_members/workspaces/drawings/result_versions/wiring/evidence 与 Agent runtime migration；托管远端环境仍待部署。
- [x] 已为本批新表编写 RLS、索引、updated_at、版本和证据约束，并通过本地真实 Supabase 的 owner/anon、并发事件序号和线号分配验证；托管远端权限仍待复验。
- [x] 实现项目列表/项目树/图纸详情 API，真实只读库与临时项目登录查询通过。
- [x] 实现私有 `project-assets` Bucket、稳定项目资产路径和签名 URL，并保留旧公开 `images` Bucket 作为迁移期兼容数据。
- [ ] 编写旧 `wiring_tables` 到新模型的回填脚本。

退出条件：前端树形目录完全来自数据库，用户权限隔离测试通过。

## Phase 3：导入、拆分与事件流

状态：in progress

- [ ] 2026-10-12 Web/Server 真实接入：项目/资源/JWT、表格增改删/下方预览、Agent SSE/阶段卡片实现，真实 CRUD/API/浏览器通过并清理；上传/Agent 完整链路仍待验收，详见 Server 实施记录。
  - 用户授权后的真实 CRUD/双图/事务回滚、Bucket 三阶段资源面板与图纸索引通过。真实模型浏览器上传/检测/确认后的三阶段成功落库（5 页/13 连接，约 226 秒）。浏览器退出，纠错/确认/归因待同项目续跑；自动审批服务 403 配置故障使续跑未执行。现有 Agent/test0 不改，一次性项目保留，见 Server 联调记录。

- [ ] 实现上传会话和客户端直传。
- [x] Agent Stage 1 完成后将工作区、图纸元数据和 PDF 页面图片写入数据库及私有 Storage；项目创建/上传 HTTP API 仍待业务 Server 接入。
- [x] 将新 Agent runtime、源文件缓存和 checkpoint 移出 `frontend/public`。
- [x] 接入 Supabase 持久 Run/Event/Artifact/Proposal/Checkpoint repository 与带租约的跨进程任务队列；完整进程中断续跑测试仍待补齐。
- [x] Agent API 提供阶段事件 SSE、序号续传和终态关闭；Server/Web 代理待 Phase 4/6 集成。

退出条件：服务重启后任务可续跑，前端刷新后进度不丢失。

## Phase 4：Agent Profile 模块化

状态：in progress

- [x] 2026-10-12 规则库生命周期：共享可用模板克隆新 key，人工确认创建后私有 Bucket 直接注册；所有登录用户可读，创建者删除后停用，冻结历史引用保留。共享 RLS、真实 ABB 包和应用检查已验收，见 ADR-0012 与 Server 记录。
- [x] 建立 Agent 模块按顺序开发与阶段验收清单。
- [x] 建立 `services/agent` Python 包、模块目录、健康检查和测试骨架。
- [x] 定义 `DrawingProfile`、注册表、资源 checksum 和不可变版本快照。
- [x] 建立独立 Agent API `:8100` 壳层、健康检查和 run/event/proposal 领域契约。
- [x] 建立 Model Gateway、Tool Registry、Context、Checkpoint 和 Trace 最小 Harness。
- [x] 通过 Compatibility Adapter 注册旧 ZH 流程，旧代码保持原位。
- [x] 实现只读取 PDF 首页的 Profile Router、人工确认和动态 ProfileBinding。
- [x] 提供 ZH/ABB 公开规则查询接口，供前端展示规则。
- [ ] 使用真实 VLM 完成 ZH/ABB/UNKNOWN 首页路由评测报告（生产启用门槛；不阻塞 Fake Model 下的阶段 Agent 开发）。
- [x] 按现有流程建立 Page Classifier、Page Scanner、Cross-page Resolver 三个独立子 Agent 与子图。
- [x] 通过 ZH Profile adapter 使用已迁入 Agent 的三阶段 Prompt、图片 Few-shot、解析和重试逻辑。
- [x] 将 ZH PDF 渲染、图纸索引、跨页任务、断点、确定性校验和 XLS/XLSX 输出迁入 Agent 包，由本地 runner 串联三个原生子图且不导入旧 `backend`。
- [x] 为三个阶段建立 Fake Stage Adapter 契约和失败路径测试；真实图片字段级回归仍待运行。
- [ ] 使用真实 VLM 对 ZH 固定案例做字段级结果、耗时和费用对照。
- [x] 实现 run 创建、查询、事件、SSE、Artifact、Proposal、取消和恢复控制面 API。
- [x] 建立 Agent 内部 Bearer 鉴权和 OpenAPI/Schema 契约测试；Server 调用端待 `apps/api` 建设。
- [x] 将现有 ZH Prompt、图片 Few-shot、引用解析和校验迁入 ZH Profile/Agent 包；固定案例真实模型基线另行验收。
- [x] ABB 1.1.0/1.1.1 历史资源：独立 Prompt/Few-shot/expected/task 已上传并校验；后续共享规则迁移将非候选历史包标为 active，历史 checksum 保留。
- [x] ABB 1.1.2 可执行 Profile：三个阶段图片 1/1/2 张，注册独立 `abb_native` VLM 适配器、Sheet/Cont 索引、跨页引用和确定性策略；18 文件 Bucket 读回通过，新任务默认选择 1.1.2。
- [ ] ABB 真实模型字段级质量验收：工程确认 expected、运行固定图像回归并记录字段差异、耗时和费用；可执行不等于准确率已通过。
- [x] Profile 自动检测低置信、未知或 experimental 时要求人工选择。
- [x] 公共文档 Graph 移除 ZH 规则导入和按 client 能力切换的旧拓扑；端子、方向、电流、引用与导出字段通过 Profile 策略注入。`zh_workflow` 实现与兼容目录均已移除；ABB 已注册独立策略。
- [x] 按用户要求删除相邻页分段、批量提取及关联策略/配置/checkpoint，所有提取和导出调用直接使用新模块。
- [x] 实现 Supervisor 主 Agent、受控工作流分派、阶段事件翻译和连接/图纸/工作区级 Correction Workflow；Supabase 模式已接入结果查询、Correction bundle、显式确认和版本化事务提交。
- [x] 建立阶段 0 纯 HTTP 终端验收、独立只检测/确认闭环与单进程 Supervisor 短期记忆；近期对话、附件和待确认对象注入 LLM，上下文不会由测试脚本伪造。
- [x] 编写三阶段持久化改造方案和 proposed ADR：逐项结构化提交、阶段清单、数据库读写屏障及改动文件已列明，尚未实施。
- [x] 将持久化方案/ADR 修订为 V1.1，纳入六项一致性评审约束；设计完成不等于机制已实现。
- [x] Gate A：阶段提交/读库屏障、RUNNING 接管/fencing、最终收尾、树发布、退避/取消和独立进程空缓存恢复已验证；真实 Supabase/Fake VLM 10 场景分批通过，21 份 migration 空库/合成旧数据验证通过。
- [x] Gate B 接口/Fake 验收：内部业务上传、Profile 确认后原子创建 protocol 2 run、Worker/SSE、published 项目树/结果分页/阶段摘要，以及 `1.3stage` 纯 HTTP 客户端已接通；本地 Supabase/Fake HTTP 2 场景通过。
- [ ] Gate B 真实模型人工验收：真实 PDF、人工字段 baseline、成本/耗时/差异报告；接口通过不等于准确率通过，Web/JWT 代理仍另行建设。
- [x] 串联 Supervisor V2 离线闭环：Profile Detection 内部工具、受控结果工具、`is_cross_page` 三态 Stage 2/3 纠错，以及需用户授权的 Improvement/Profile 候选链路。
- [x] 建立 Eval Harness、Profile 沙箱、确定性 Release Gate、人工审批、canary 与回滚状态机；候选、评测、门禁与审计已持久化。2026-10-12 接入服务端三阶段候选评测/receipt 与不可变 Bucket 包发布执行器，真实评测和人工发布验收待执行。
- [ ] 纠错改造：混合 `CorrectionBatch`、统一跨页 Stage 2→Stage 3、Profile 资源包适配器和归因上下文已实现；本地 `20261011010000` 迁移和 ZH bootstrap 已发布，待 API/Worker 开启远端包模式、test0 人工验收及纠错 RUNNING 接管。
- [x] 修复案例 A 的 Supervisor Schema 边界：支持起点/终点精确查询、数字页码/线号归一化和完整 JSON Schema 提示；只读真实模型路由与唯一连接查询通过，实际 proposal/提交验收仍由用户继续。
- [x] 案例 A 用户确认已创建 accepted 版本 2；修复提交后归因 source document 外键引用和成功结果报错边界。归因任务实际补启动及后续建议验收待用户重载服务后执行。
- [x] 用户调整后的原位纠错代码和本地 migration 已完成：直接值/Stage 2/3 结果共用稳定连接 ID 更新，revision/审计/幂等保留；服务重载后的真实人工验收待执行，旧历史不删除。
- [x] 纯 HTTP 混合纠错终端验收及只读模型输出接口已实现：人工确认、规则无问题判定、意外候选拒绝，离线回归通过；规则问题使用 `--expect-rule-issue`，既有候选由 `run_rule_release.py` 接续评测、审核与发布。真实完整链路待人工验收。
- [x] 按用户要求完成 test0 三条真实图纸核对和终点端子人工注错，保存混合消息/字段级预期/可恢复备份；实际混合 Agent 执行和规则判定未运行，不以数据准备代替验收。
- [x] 修复用户混合验收暴露的纠错起点匹配：位置/设备/端子分开比较，缺失/歧义/重复不再静默漏修，Worker 安全日志定位异常；33 项相关离线测试和保存的 Stage 2 产物只读重放通过。真实 Stage 3/确认提交/归因链路仍待用户重载后以新会话验收。
- [x] 混合验收后续记录已通过 Stage 2/3、原位提交和人工预期字段检查；修复随后暴露的 Improvement 输出 Schema 缺失，24 项相关离线回归通过。真实归因/规则判定待重载后单独恢复失败归因 run，不重复线表修订。

退出条件：新增模板不改 Graph 拓扑；ZH 与 ABB 回归分别通过。

## Phase 5：结果管理与导出

状态：in progress

- [x] 完整提取通过原子 RPC 写入 `result_versions/wiring_units/wiring_connections/evidence`，并保留 `is_cross_page`、来源证据、Profile/模型和 Proposal 关联。
- [x] 实现 Server 结果分页/筛选/稳定排序/来源与跨页定位、待复核字段；端子增改删及审计，真实临时项目通过。专用待复核工作队列不在本轮范围。
- [x] Agent/Supervisor 侧实现强类型行级修订、乐观版本校验、accepted feedback 与审计；外部业务 API 尚待接入。
- [ ] 从结果版本生成 XLSX，并做字段和顺序一致性测试。
- [ ] 下线前端从 `public/library` 和整包 JSONB 聚合结果的逻辑。

退出条件：数据库为唯一业务事实来源，导出可复现。

## Phase 6：反馈与 Agent 演进

- [x] 2026-10-12 目标评测定位修复：评测应用层向 Stage 2 传递冻结起点身份，不提供正确终点，严格匹配/发布门禁不变；32 项相关离线回归通过。真实评测、失败候选的新评测入口仍待验收/实现，不复用旧失败报告声称重测成功，见 Agent 修复记录。

- [x] 2026-10-12 规则补丁解析修复：JSON 字符串内嵌 fence 不再被误截；31 项离线回归与实际失败 Trace 重放通过，真实恢复/评测/发布仍待用户验收。

- [x] 2026-10-12 补丁生成输出契约：ProfilePatchBuilder 动态 Schema/纯 JSON/完整文件转义约束，离线回归通过；真实失败归因任务恢复、评测和发布仍待验收。

状态：planned

- [ ] 实现线表、图纸、工作区三级反馈入口。
- [x] Agent 侧区分数据修订和规则建议，并持久化 Correction bundle、accepted feedback 和审计；面向 Web 的反馈 API 尚待接入。
- [x] Agent 侧已持久化候选、离线评测、人工门禁、canary 和回滚状态；服务端评测及两次确认的 Bucket 发布执行器已实现，49 项离线回归通过，真实评测/发布/回滚待人工验收。
- [x] 本地私有 Bucket 已部署并发布 ZH Prompt/Few-shot/expected/rules/schema 不可变 bootstrap 包；Improvement/候选适配器已实现。运行 API/Worker 开关、完整候选发布/回滚人工验收仍待执行。
- [ ] 接入真实文档问答前，先完成权限、引用和防幻觉设计。

退出条件：规则变更可审计、可评测、可回滚，不由单次对话直接上线。

## Phase 7：清理与上线

状态：planned

- [ ] 回填并核对历史项目。
- [ ] 删除旧 Vite、旧接口和 `frontend/public/library` 业务依赖。
- [ ] 完成性能、并发、费用、安全和灾备测试。
- [ ] 更新部署、运维和用户手册。

退出条件：新链路稳定运行，旧链路无调用且已有可回滚备份。
