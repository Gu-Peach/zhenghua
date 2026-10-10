# Changelog

本文档记录对产品行为、架构、数据模型和开发流程有影响的变化。纯格式调整无需记录。

## 2026-10-09

### Changed

- 将线表目标模型细化为端子排线号单元与端子连接明细：核心 Agent 字段改为可查询列，项目/工作区/业务页码通过外键和扁平视图提供检索；线号由数据库在结果版本内从 1000 分配。新增 migration 尚未应用远端，旧 `wiring_tables` 保持不变。
- 增加连接级 `is_cross_page` 三态字段（`same_page/cross_page/unknown`），用于 Stage 2 结果与局部纠错路由；不新增跨页专用表。
- 完成 Supervisor 串联 V2 的离线实现：Profile Detection 内部工具、受控多条件结果查询与版本提交、Stage 2/3 局部纠错、accepted feedback 归因、规则候选显式授权、沙箱构建及评测门禁。真实 Supabase/业务 Server 适配器仍待接入。
- 将 `apps/web` Supervisor 调整为显式开启的 Mock 运行模拟：未触发时不展示处理过程，思考文本流式淡化输出，Agent 阶段按等待/完成状态依序呈现；真实 Agent/SSE 后端仍待联调。
- 在线表格仅对明确标记的跨页索引终点提供悬浮高亮和目标图纸定位。
- 项目工作台新增图纸库文件夹视图与隔离的 ZH/ABB 规则库视图；规则修订先展示候选，不直接发布生产 Profile。
- 将图纸库/规则库移动到项目顶部导航，主操作改为 PDF 上传；线表修复使用自然语言请求和显式模拟开关。上传 PDF 后先登记源文件，Stage 1 完成后才显示工作区及拆分页。

## 2026-10-08

### Added

- 新增 React + Vite + TypeScript、FastAPI、Agent Worker 的 monorepo 目标架构。
- 新增 `apps/web` 静态工作台、标准源码分层与类型化 Mock API。
- 新增独立 Agent 服务 `:8100`、多 Agent Graph、反馈局部重提取和 Eval Harness 设计。
- 新增“项目 -> 工作区 -> 图纸”的产品与数据层级。
- 新增登录、用户菜单、三栏项目工作台和静态 AI 对话栏需求。
- 新增可插拔 `DrawingProfile` 方案，用于隔离 ZH、ABB 和后续图纸标准。
- 实现独立 Agent 服务 M0-M3：服务壳层、领域契约、Harness、Profile Registry 与旧 ZH 兼容适配器。
- 实现 M4 首页 Profile Router、用户确认、动态规则绑定和 Profile 规则查询接口。
- 新增 Supervisor 主 Agent 与 Correction Workflow 的架构决策、结构化契约、意图决策骨架、工作流 allowlist 和确定性纠错路由器；完整 Graph 与事件闭环排在 Extraction Workflow 之后。
- 新增 Stage 1/2/3 独立提取 Agent、Pydantic 契约和 LangGraph 子图；ZH 通过 adapter 复用原 VLMClient、Prompt、图片 Few-shot、parser 与重试，不改旧提取逻辑。
- 新增结构化数据库、结果版本、来源证据、用户反馈和 Profile 发布模型。
- 新增 `docs/roadmap.md`、`docs/TODO.md` 和根目录 `AGENTS.md`。

### Changed

- 将数据库定义为业务事实来源，`frontend/public/library` 调整为迁移期兼容目录。
- 将 XLSX 定义为结果版本的派生产物，不再作为唯一结果。
- 将长任务目标执行方式从 FastAPI `BackgroundTasks` 调整为独立持久 Worker。
- `docs/` 纳入版本控制，以便持续记录路线、变更和待办。
- 前端模块开发记录改为归档到 `docs/apps/web/`。
- Agent 在线修复只生成结果补丁；生产结果由业务 Server 校验并创建新版本。

### Preserved

- 保留现有 PDF 300 DPI 渲染、三阶段 LangGraph、Few-shot 和断点续跑能力。
- 在新链路通过验收前保留旧 Vite 前端和旧 API。
