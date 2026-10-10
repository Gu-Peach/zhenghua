# TODO

> 这是当前执行清单，不替代 [开发路线](./roadmap.md)。每次开发只把本次可交付内容放入“进行中”。

## 进行中

- [x] 从保留的 `.git-new` 恢复本地 Git 历史和 origin，整理当前源码、文档及版本化 Few-shot 资产，排除密钥、缓存和提取运行产物。

- [ ] 按六项评审意见修订三阶段持久化方案/ADR：Worker 接管、权威预期集合、最终收尾、项目树发布、双摘要幂等和两层验收；本轮仅改文档。
- [x] 排查 Codex 新模型不可见问题：核对官方发布、客户端版本、配置优先级、模型目录来源与账号返回，并在需要时备份和刷新自定义目录。
- [ ] 将规范化线表 migration 应用到远端 Supabase，并执行空库、权限、线号并发和旧数据快照验证。
- [ ] 完成 Agent M8 剩余生产化：完整中断续跑测试和 ZH 真实字段级基线；Supabase 持久 repository 与跨进程租约队列已完成。
- [ ] 解除 Agent M15-M16 阻塞：补齐 ABB 独立真实资产，并先建设 `apps/api`、业务持久化与 Server 事件代理。
- [ ] 使用真实 VLM 完成 Agent M4 首页路由准确率、耗时和费用验收。
- [ ] 审核并确认 `docs/refactor-plan.md` 的领域模型与迁移顺序。
- [ ] 为 ZH、ABB 各建立一份不可变的验收案例清单。
- [ ] 接入 Supabase Auth，并实现真实路由守卫和会话恢复。
- [ ] 用新 `apps/api` 替换 `src/apis` 的 Mock 适配器。
- [ ] 评审独立 Agent 服务的端口、Server 契约和数据所有权。
- [x] 评审多 Agent 提取、反馈重提取和离线自完善方案。
- [ ] 确认 Agent Harness 的 V1 边界与 Profile 发布门禁。

## 下一步

- [ ] 初始化 monorepo 根配置。
- [ ] 创建 FastAPI 新模块目录和兼容适配层。
- [x] 设计并评审 Supabase 新迁移和 RLS。
- [ ] 用真实 API 替换 mock 数据。
- [x] 将 Agent runtime/checkpoint 迁出 `frontend/public`。

## Agent

- [ ] 评审并实施三阶段持久化方案：数据库逐项结果与阶段清单、严格提交/读取屏障、无缓存续跑，再接入 `1.3stage` 纯 HTTP 验收；设计文档已完成，代码/migration 未开始。
- [ ] 严格按 M0-M16 顺序实现并逐阶段验收 Agent，不并行跳过依赖门槛。
- [x] 预先建立 Supervisor/Correction 架构决策、领域契约、意图决策骨架和确定性纠错路由；Supervisor Graph 后续开发。
- [x] 建立 Stage 1 页面分类、Stage 2 当前页扫描、Stage 3 跨页补全独立 Agent 子图，并通过 ZH adapter 复用原流程。
- [x] 完成 Agent M0-M3：服务骨架、公共契约、Harness、Profile Registry 与 ZH 兼容适配器。
- [x] 定义 `DrawingProfile` Protocol 和 Profile Registry。
- [x] 将 ZH Prompt、图片 Few-shot、PDF/索引/跨页/校验/XLSX 工作流迁入 `services/agent`，并提供无 backend 导入的三阶段测试 runner。
- [x] 为 VLM HTTP 错误增加脱敏 provider 详情；不可重试的请求错误立即终止工作流，避免整本 PDF 重复发送无效请求。
- [x] 将 ZH Stage 1/2/3 当前页和 Few-shot 图片的 OpenAI `image_url.detail` 设为 NInfer 兼容的 `auto`。
- [x] Agent dotenv 配置仅加载 `services/agent/.env`；根目录和 `backend/.env` 不再参与配置合并。
- [x] 修复 Stage 2/3 图片 Few-shot 超出 VLM 视觉 patch 预算的问题；请求内按配置缩小样例图，保留所有图像样例及原始图纸分辨率。
- [ ] 使用真实 VLM 对 ZH 固定案例做字段级结果、耗时和费用对照。
- [ ] 完成 ABB 三阶段 Prompt、图片 Few-shot 和 Expected JSON。
- [ ] 增加 Profile 识别结果和人工覆盖字段。
- [x] 通过 repository 接口保存阶段事件并提供可续传 SSE；Supabase 模式已接入持久 Run/Event/Artifact/Proposal/Checkpoint repository 和租约队列。
- [x] 增加节点级幂等键、Run 创建幂等和任务取消检查。

## 数据与结果

- [x] 新建规范化领域表，不修改旧 `wiring_tables` 数据。
- [x] 定义 Connection 与 Evidence 的字段映射。
- [ ] 实现服务端分页、筛选和排序。
- [ ] 实现结果版本和 XLSX 快照导出。
- [ ] 编写旧数据回填与核对报告。

## 待决策

- [ ] 项目是否支持多人协作，还是 V1 仅 owner 可见。
- [ ] 工作区名称是否允许用户覆盖 Agent 识别值。
- [ ] ABB 图纸页号和跨页坐标的统一业务键。
- [ ] Profile 自动识别低于多少置信度时要求人工选择。
- [ ] 生产部署采用自管 Redis/Celery，还是托管队列。

## 已完成

- [x] 编写三阶段持久化改造方案及 proposed ADR-0007：逐轮数据结构、数据库/Storage 位置、事务/恢复边界、最终字段映射、改动文件与验收顺序；本轮仅交付文档。
- [x] 建立阶段 0 纯 HTTP 终端验收脚本、会话附件接口、Supervisor 短期记忆与检测后确认闭环；103 项 Agent 测试、strict mypy、Ruff 与 compileall 通过，默认测试不调用真实 VLM。短期记忆限定为单进程最近 12 回合，长期记忆仍未实现。
- [x] 修复真实 OpenAI-compatible 模型请求中结构化 Supervisor 消息的 `content` 类型，并以请求体回归覆盖 mapping 序列化；重新执行阶段 0 前需让 Agent 服务加载修复后的代码。
- [x] 兼容不支持 provider structured-output 的 OpenAI-compatible 模型端点：默认不发送 `response_format`，保留本地 JSON/Pydantic 校验；完成离线回归，阶段 0 真实重试需重载 Agent 服务。

- [x] 删除 `agent_service/zh_workflow` 全部兼容文件与缓存目录，旧路径测试切换到新模块；93 项默认测试及全包 strict mypy/Ruff/编译检查通过。
- [x] 删除 Agent 旧相邻页分段、批量提取及独占辅助代码、配置、checkpoint 和兼容入口；正式链路只使用新三阶段 Graph。93 项默认测试及全包 strict mypy/Ruff/编译检查通过。
- [x] 完成 `zh_workflow` 实现迁移：公共文档 Graph、共享 domain 结果、PDF/checkpoint/导出基础设施与 ZH 确定性策略分离；正式提取使用新模块，兼容目录已在后续清理中删除。新增非空 PDF 字段/跨页/恢复与导出回归，全包 strict mypy/Ruff 通过。
- [x] 完成 Agent 结构化结果落库：完整提取 Proposal 原子提交为 `result_versions/wiring_units/wiring_connections/connection_evidence`；数据库从 1000 分配线号，提交具备幂等、base version 校验和事务回滚。
- [x] 将 Supabase 模式下的 Correction bundle、accepted feedback、Model Trace、Profile candidate、release gate、eval 与发布审计迁移为持久适配器；跨进程 Correction 图片从私有 Storage 重新物化。
- [x] 建立受控结果读写 RPC：Supervisor 只通过强类型参数检索和确认 Proposal，禁止任意 SQL/字段写入；局部修订仅在用户确认后创建新的 accepted 结果版本。
- [x] 打通 Agent 本地真实 Supabase 生产基础：应用规范化与 Agent runtime migration，建立私有 `project-assets` Bucket，按项目/工作区/图纸保存原始 PDF 与页面图片，接入持久 Run/Event/Artifact/Proposal/Checkpoint/SourceDocument repository 和跨进程租约队列；真实冒烟覆盖 checksum、RLS、签名 URL、并发事件序号、乐观锁与 1000 起线号分配。
- [x] 按 Supervisor Agent 串联方案 V2 完成离线实现：Profile Detection 内部工具、`is_cross_page` 三态纠错、受控结果查询/版本提交、accepted-feedback Improvement、用户授权后 Profile 候选构建，以及全链路 Fake 测试；Supabase adapter 已在后续任务完成，Web/Server 集成仍待建设。
- [x] 定义并新增规范化线表 migration：项目/工作区/图纸/结果版本、端子排线号单元、端子连接明细、证据、RLS、索引与扁平检索视图；旧 `wiring_tables` 保持不变。
- [x] 完成 Agent M8 离线控制面基础：Run/Worker、阶段 Artifact/Event、ResultProposal、取消/恢复和 SSE。
- [x] 完成 Agent M9-M10 离线基础：Supervisor Graph、事件消息映射、受控工具与局部 Correction Workflow。
- [x] 完成 Agent M11-M14 离线基础：反馈归因、Profile 沙箱候选、离线评测、人工发布门禁、canary 和回滚状态机。
- [x] 盘点 M15/M16 前置条件并记录阻塞：ABB 资产仍混有 ZH 规则；Agent 生产持久化已完成，但 `apps/api` 与 Web 事件代理尚未形成可用链路。
- [x] 记录原始产品需求。
- [x] 给出目标 monorepo、数据库、前端和 Agent 架构。
- [x] 建立开发规范和文档维护机制。
- [x] 在 `apps/web` 初始化 React + Vite + TypeScript 静态前端。
- [x] 实现登录页、项目工作台三栏布局和初始静态 AI 会话原型。
- [x] 实现 `apis/assets/components/directives/hooks/layout/router/stores/views` 分层。
- [x] 实现项目、工作区、图纸树及线表 Mock 数据契约。
- [x] 通过类型检查、ESLint、生产构建与桌面浏览器交互验收。
- [x] 在 `docs/apps/web` 归档前端架构和阶段记录。
- [x] 实现图纸库/规则库、跨页终点定位、Supervisor Mock 事件流与自然语言修复入口。
- [x] 使用 Playwright 验证 PDF 三阶段、带答案直接修订、Stage 2/Stage 3 路由、规则候选和桌面/窄屏布局。
- [x] 收紧 Mock Supervisor 触发和拆分页时序：初始无 Agent 过程，模拟关闭时仅登记 PDF，Stage 1 完成后才出现工作区/图纸，Agent 依序显示运行等待和完成勾选。
- [x] 将图纸库/规则库移动到项目顶部导航，将重新处理改为 PDF 上传，并将修复入口改为自然语言与显式模拟开关。
- [x] 规划 Agent 与业务 Server 独立部署及 `8100` 内部端口。
- [x] 设计 Supervisor、Profile Detection、Extraction、Correction、Improvement 协作架构。
- [x] 设计 Server-Agent run/event/proposal 契约和数据所有权。
- [x] 设计连接、图纸、工作区级局部重提取与字段级 diff。
- [x] 设计 Agent Harness、问题归因、离线评测和 Profile 发布门禁。
- [x] Agent 服务可在 `8100` 独立启动，并提供 live/ready/Profile 查询接口。
- [x] Agent M0-M3 的 20 个默认测试、严格类型检查和 Ruff 验收通过。
- [x] 实现 M4 首页 Profile Router、人工确认、动态 ProfileBinding 和公开规则接口。
- [x] M4 的 27 个默认测试、真实 PDF 首页渲染、严格类型检查和 Ruff 验收通过。
