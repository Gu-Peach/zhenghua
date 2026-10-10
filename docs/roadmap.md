# 开发路线

> 最后更新：2026-10-10
> 状态含义：`planned`、`in progress`、`blocked`、`done`

## Phase 0：基线与规范

状态：in progress

- [x] 整理产品需求与目标架构。
- [x] 建立文档索引、CHANGELOG、TODO 和 `AGENTS.md`。
- [x] 恢复正常本地 Git 仓库及原远程关联，补齐运行产物忽略规则和 Agent Few-shot 图片跟踪规则；业务阶段状态保持不变。
- [ ] 固化 ZH 当前案例的结果基线、耗时和费用基线。
- [ ] 固化 ABB 的分类、页扫描和跨页 Few-shot 回归集。
- [ ] 为现有 API 导出 OpenAPI 快照。

退出条件：需求、数据模型、迁移策略和当前质量基线可复核。

## Phase 1：Monorepo 与 Vite 壳层

状态：in progress

- [x] 创建 `apps/web`、`apps/api`、`services/agent`、`services/server` 基础边界。
- [ ] 配置 pnpm workspace、Turbo、TypeScript、Python `pyproject.toml`。
- [x] 配置 pnpm workspace、Vite 和 TypeScript strict mode。
- [x] 建立 React Router 静态登录页和应用布局。
- [ ] 接入 Supabase Auth 与受保护路由守卫。
- [x] 实现 Header、三栏工作台和初始静态 AI 会话原型。
- [x] 完成交互 Mock 工作台：图纸库/规则库、跨页端子定位、自然语言修复与显式模拟开关；无触发时为空态，PDF 上传后按 Stage 1/2/3 顺序流式展示 Agent 状态，Stage 1 完成后才呈现工作区和拆分页（真实 API、鉴权和持久化 SSE 待后续阶段）。
- [x] 保留旧 Vite 前端作为迁移期 fallback。

退出条件：用户可登录并进入空项目工作台；CI 可构建 Web 和 Python 包。

## Phase 2：项目领域与数据库

状态：in progress

- [x] 已编写并应用本地 Supabase 的 projects/project_members/workspaces/drawings/result_versions/wiring/evidence 与 Agent runtime migration；托管远端环境仍待部署。
- [x] 已为本批新表编写 RLS、索引、updated_at、版本和证据约束，并通过本地真实 Supabase 的 owner/anon、并发事件序号和线号分配验证；托管远端权限仍待复验。
- [ ] 实现项目列表、项目树、图纸详情 API。
- [x] 实现私有 `project-assets` Bucket、稳定项目资产路径和签名 URL，并保留旧公开 `images` Bucket 作为迁移期兼容数据。
- [ ] 编写旧 `wiring_tables` 到新模型的回填脚本。

退出条件：前端树形目录完全来自数据库，用户权限隔离测试通过。

## Phase 3：导入、拆分与事件流

状态：planned

- [ ] 实现上传会话和客户端直传。
- [x] Agent Stage 1 完成后将工作区、图纸元数据和 PDF 页面图片写入数据库及私有 Storage；项目创建/上传 HTTP API 仍待业务 Server 接入。
- [x] 将新 Agent runtime、源文件缓存和 checkpoint 移出 `frontend/public`。
- [x] 接入 Supabase 持久 Run/Event/Artifact/Proposal/Checkpoint repository 与带租约的跨进程任务队列；完整进程中断续跑测试仍待补齐。
- [x] Agent API 提供阶段事件 SSE、序号续传和终态关闭；Server/Web 代理待 Phase 4/6 集成。

退出条件：服务重启后任务可续跑，前端刷新后进度不丢失。

## Phase 4：Agent Profile 模块化

状态：in progress

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
- [ ] 建立 ABB Profile，使用圆圈放线标志和 ABB 独立案例。
- [x] Profile 自动检测低置信、未知或 experimental 时要求人工选择。
- [x] 公共文档 Graph 移除 ZH 规则导入和按 client 能力切换的旧拓扑；端子、方向、电流、引用与导出字段通过 Profile 策略注入。`zh_workflow` 实现与兼容目录均已移除；ABB 策略注册仍需独立资产验收。
- [x] 按用户要求删除相邻页分段、批量提取及关联策略/配置/checkpoint，所有提取和导出调用直接使用新模块。
- [x] 实现 Supervisor 主 Agent、受控工作流分派、阶段事件翻译和连接/图纸/工作区级 Correction Workflow；Supabase 模式已接入结果查询、Correction bundle、显式确认和版本化事务提交。
- [x] 建立阶段 0 纯 HTTP 终端验收、独立只检测/确认闭环与单进程 Supervisor 短期记忆；近期对话、附件和待确认对象注入 LLM，上下文不会由测试脚本伪造。
- [x] 编写三阶段持久化改造方案和 proposed ADR：逐项结构化提交、阶段清单、数据库读写屏障及改动文件已列明，尚未实施。
- [ ] 按评审方案实现数据库阶段屏障、跨进程无缓存恢复和 `1.3stage` 纯 HTTP 全链路验收。
- [x] 串联 Supervisor V2 离线闭环：Profile Detection 内部工具、受控结果工具、`is_cross_page` 三态 Stage 2/3 纠错，以及需用户授权的 Improvement/Profile 候选链路。
- [x] 建立 Eval Harness、Profile 沙箱、确定性 Release Gate、人工审批、canary 与回滚状态机；候选、评测、门禁与审计已持久化，实际 Profile 文件部署执行器仍待接入。

退出条件：新增模板不改 Graph 拓扑；ZH 与 ABB 回归分别通过。

## Phase 5：结果管理与导出

状态：planned

- [x] 完整提取通过原子 RPC 写入 `result_versions/wiring_units/wiring_connections/evidence`，并保留 `is_cross_page`、来源证据、Profile/模型和 Proposal 关联。
- [ ] 实现结果分页、筛选、排序、来源定位和待复核视图。
- [x] Agent/Supervisor 侧实现强类型行级修订、乐观版本校验、accepted feedback 与审计；外部业务 API 尚待接入。
- [ ] 从结果版本生成 XLSX，并做字段和顺序一致性测试。
- [ ] 下线前端从 `public/library` 和整包 JSONB 聚合结果的逻辑。

退出条件：数据库为唯一业务事实来源，导出可复现。

## Phase 6：反馈与 Agent 演进

状态：planned

- [ ] 实现线表、图纸、工作区三级反馈入口。
- [x] Agent 侧区分数据修订和规则建议，并持久化 Correction bundle、accepted feedback 和审计；面向 Web 的反馈 API 尚待接入。
- [x] Agent 侧已持久化候选、离线评测、人工门禁、canary 和回滚状态；生产 Profile 文件部署执行器仍待实现。
- [ ] 接入真实文档问答前，先完成权限、引用和防幻觉设计。

退出条件：规则变更可审计、可评测、可回滚，不由单次对话直接上线。

## Phase 7：清理与上线

状态：planned

- [ ] 回填并核对历史项目。
- [ ] 删除旧 Vite、旧接口和 `frontend/public/library` 业务依赖。
- [ ] 完成性能、并发、费用、安全和灾备测试。
- [ ] 更新部署、运维和用户手册。

退出条件：新链路稳定运行，旧链路无调用且已有可回滚备份。
