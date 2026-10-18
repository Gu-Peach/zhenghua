# apps/web 前端归档

- [关闭提取未完成提示](./changelog/2026-10-18-extraction-notice-dismiss.md)：右侧关闭按钮、键盘操作、新失败重新展示，不改任务状态。

- [Explain逐行修改预览](./changelog/2026-10-18-explain-edit-preview.md)：先回答后预览、确认/拒绝、冲突/处理态保护及刷新/恢复；75项全量与后续6项定向通过。

- [查看规则双击编辑与旁侧助手](./changelog/2026-10-18-profile-rule-editing.md)：图片/实际结果诊断、工具/差异展示、确认后发布替换新版与失败恢复。

- [规则负例可选提示](./changelog/2026-10-17-profile-optional-negative.md)：负例上传保留，未提供也可发布。

- [补全聊天回到初扫修正](./changelog/2026-10-17-profile-scan-correction.md)：跟随Agent阶段回退、展示修正端点并重新确认，11项规则聊天回归通过。

- [规则模型错误类别展示](./changelog/2026-10-17-profile-model-errors.md)：前端显示code/诊断编号，同轮重试及桌面/窄屏失败态验证。

- [分类阶段PDF随机抽样](./changelog/2026-10-17-profile-pdf-sampling.md)：上传后自动抽两页、两份Expected、缓存说明/重试，后两阶段继续人工图片；60项浏览器通过。

- [引导式规则聊天](./changelog/2026-10-17-profile-conversation.md)：图片/文字追问、逐阶段候选/修正/确认、持久对话恢复和手动发布；57项浏览器及最后12项入口回归通过。

- [Profile三步创建向导](./changelog/2026-10-17-profile-wizard.md)：图片/规则生成答案、表格编辑确认、恢复和手动发布；6项新增/共51项离线浏览器、前端检查及截图通过。

- [线表与图纸可调宽面板](./changelog/2026-10-17-preview-resize.md)：拖拽/键盘调宽、双击复位、缩放数字及长标题防溢出；45项离线浏览器和前端检查通过。

- [智能体中心与图纸校验工作台](./changelog/2026-10-17-agent-center-preview.md)：三Agent/提取Skills，默认全量与五列预览、上下双图和归一化坐标标记，44项浏览器及前端检查通过。

- [项目名原地编辑与目录升序](./changelog/2026-10-17-project-tree-inline.md)：侧栏/标题双击编辑、工作区与图纸自然升序、编号简名；32项浏览器回归及前端检查通过，后端不变。

- [来源解释逐字缓冲与Markdown](./changelog/2026-10-17-explain-typewriter.md)：大块/完成事件也逐字显示、立即显示/停止/减少动态效果，26项浏览器回归及前端检查通过，仅前端修改。

- [独立来源解释浮窗](./changelog/2026-10-17-explain-panel.md)：行/页悬停、流式工具与图纸、追问/取消/重试，22项浏览器回归及前端检查通过，运行需加载8000/8100新代码。

- [提取阶段等待、增量目录与线表展示](./changelog/2026-10-16-incremental-extraction.md)。

2026-10-16结果接口的两端坐标已透传到WiringRow类型，保留独立PDF物理页；本轮仅元数据，无可视布局变化或图片高亮。见[Server坐标记录](../../service/server/changelog/2026-10-16-terminal-coordinates.md)。

2026-10-16登录入口改为直接进入工作区，空库也保留完整工作区布局；13项浏览器与Web检查通过，见[记录](./changelog/2026-10-16-workspace-entry.md)。

2026-10-16当前已切换三表数据管理，上传仅保存、Agent/AI后续接入；10项浏览器夹具与类型/lint/build通过，见[交付](./changelog/2026-10-16-simple-management.md)。下文2026-10-13 Agent工作流为历史状态。

2026-10-13 对话入口微调：日常公开回复累积显示，任务先说明后卡片；21项浏览器HTTP夹具及Web类型/lint/build通过，桌面/窄屏已检查。见[记录](./changelog/2026-10-13-supervisor-chat.md)。

2026-10-13 规则改进取消评测门禁，聊天展示一次确认直接修改/启用及成功结果；详见 [跨模块记录](../../service/agent/changelog/2026-10-13-confirmed-rules.md)。

> 当前状态：Supabase Auth、三表数据管理和规则引用预览已接入；Agent提取/事件流尚未改接新表。
> 应用说明：[apps/web/README.md](../../../apps/web/README.md)

## 所有权

`apps/web` 是新 React + Vite + TypeScript 前端。旧 `frontend/` 在迁移期保留，不作为新代码的依赖。

源码边界：

- `apis`：请求 Client、接口函数、DTO、Mock 适配；
- `assets`：全局样式与打包资源；
- `components`：可复用业务组件；
- `directives`：预留底层 DOM 行为适配；
- `hooks`：可复用交互状态；
- `layout`：应用布局；
- `router`：React Router 路由和后续守卫；
- `stores`：跨页面状态；
- `views`：路由页面。

## 当前页面

- `/login`：Supabase Auth 登录、续期和错误状态；
- `/projects/:projectId`：项目工作台；
- 左侧：可折叠项目、工作区、图纸树；点击项目名称/文件夹直接切换该项目数据，当前项目箭头单独控制折叠；项目下面直接显示工作区，不显示 PDF 文件名节点或二次“打开项目”入口；
- 项目目录按创建时间/ID 固定顺序，切换不将选中项目置顶；已知项目切换时保留 Header/目录/导航，仅中间数据加载，摘要更新保持原位置；
- 顶部：当前项目名称及线表工作区、图纸库、规则库导航；去掉重复项目概览；操作区上传 PDF 或导出结果；
- 中间：Server 分页线表和图纸证据；最右侧加号打开原新增端子表单，移除全部工作区按钮和结果统计副标题；跨页终点支持悬浮高亮及目标页定位；
- 顶部资源导航、线表搜索各自在所属容器居中；记录双击/行编辑按钮直接在表格内修改，Enter 保存、Esc 取消、Tab 移动，页码/线号只读；保存失败保留草稿，沿用冻结 revision/record_version、幂等与审计；
- 图纸库：按当前项目名称→工作区文件夹→图片逐级展开；展开图片后在目录内预览，不修改线表范围或切换路由；
- 规则库：从 `/api/v1/rule-library` 查询所有登录用户共享的可用资源包；每个规则标识展示最新版本，不显示草稿状态；
- 右下角：AI 聊天按钮控制悬浮窗口，消息区展示真实任务阶段、确认与结果；移除独立当前阶段卡片。普通项目初始收起，上传新 PDF 时打开确认提示，关闭窗口保留草稿和任务订阅；
- Header：处理状态、通知、用户菜单与退出入口。

## 数据与可见性

- 图纸目录来自项目详情 API 的 workspaces/drawings；图片展开时通过 projectApi 按需读取签名链接，复用 DrawingPreview 缩放和链接刷新。
- 规则库由 Server 使用当前登录用户 JWT 查询 `profile_resource_packages`，不是扫描前端或本地 `prompts/` 文件夹。
- Supabase RLS 允许所有 authenticated 用户读取 `candidate_id is null` 的手工规则包；Improvement 隔离候选仍只对创建者/审核者可见。删除仍仅创建者可执行。
- ABB 最新规则为 `abb@1.1.2`，状态 active；旧 1.1.0/1.1.1 checksum 保留。前端展示最新版本，Agent 新任务也选择最新 active 版本。

## 检查

2026-10-13 项目切换：延迟目标详情期间保留框架且不显示旧线表，来回切换不重拉目录、不因 updated_at 更新而换位置；17 项浏览器夹具、29 项 Server 默认测试及 Web 检查通过。加载中桌面/窄屏截图已检查，见 [记录](./changelog/2026-10-13-stable-project-switch.md)。

2026-10-13 原位编辑/居中：16 项浏览器夹具及 typecheck/lint/build 通过，覆盖不打开编辑弹窗、Enter/Esc/Tab、失败重试同 key、空值、后台刷新后的旧基线冲突拒绝和跨页预览；桌面/窄屏编辑截图已检查。见 [交付记录](./changelog/2026-10-13-centered-inline-edit.md)。

2026-10-13 工作台精简：13 项浏览器夹具及 typecheck/lint/build 通过，验证项目折叠/PDF 节点移除、加号打开新增表单、独立当前阶段卡片移除和原事件/确认链路；桌面/窄屏截图已检查。见 [精简记录](./changelog/2026-10-13-workbench-cleanup.md)。

2026-10-13 图纸目录/悬浮聊天：13 项浏览器夹具及 typecheck/lint/build 通过，覆盖目录展开不导航、懒加载、权限失败重试、聊天草稿与隐藏期间任务订阅、上传类型确认和纠错确认；桌面/390px 窄屏截图已检查。见 [交付记录](./changelog/2026-10-13-directory-floating-chat.md)。

质量检查和浏览器夹具命令见 [应用 README](../../../apps/web/README.md)。Playwright 的图纸目录与共享规则状态测试使用 HTTP fixtures，不调用真实模型或修改数据库。

2026-10-12 最终检查：Web typecheck、lint、production build 和 11 项 `workbench.spec.ts` 回归通过；检查登录、工作台和图纸库桌面/窄屏截图。图纸库覆盖空目录与跨工作区点击定位；共享规则 RLS 已用非创建者 authenticated 身份在真实本地 Supabase 验证。详见 [资源目录收尾记录](./changelog/2026-10-12-resource-library.md)。
