# Web 前端

2026-10-20完成行隐藏状态标记，工具栏一键审核当前目录/搜索全部分页。API2.16.0及本地迁移已就绪，重载8000刷新Web使用，见[交付](../../docs/apps/web/changelog/2026-10-20-bulk-review.md)。

2026-10-20线表仅待复核行显示透明确认勾号，双击编辑；新增端子改为表内草稿，来源聊天右下角支持缩放。复核需8000加载API2.15.0后刷新Web，本地迁移已安装，见[交付](../../docs/apps/web/changelog/2026-10-20-inline-review.md)。

2026-10-20 重扫任务卡新增本轮字段要求/预期起点与复核提示，变更条数不代表识别全部完成；API2.14.0类型同步，历史任务保持可读。需先重载8000/8100/实际Worker并刷新Web新建重扫，无迁移，见[交付](../../docs/apps/web/changelog/2026-10-20-rescan-requirements.md)。

2026-10-20 Explain只保留聊天与上传图标，图片先暂存、发送后归入本轮消息并清空草稿，下一轮不带旧图，原轮重试复用附件。刷新Web重开窗口；图片视觉输入/工具补调另需重载8100，无迁移/8000变化，见[交付](../../docs/apps/web/changelog/2026-10-20-explain-chat-images.md)。

主助手历史列表每行提供×，直接永久删除对应会话。删其他历史保留当前草稿和附件；删当前回到新对话，失败可重试。依赖API2.13.0与20261019050000迁移，本地已加载，刷新Web即可。见[历史删除交付](../../docs/apps/web/changelog/2026-10-19-assistant-history-delete.md)。

2026-10-19界面统一为浅色紧凑工具风格：用户右侧气泡、助手头像/名称、灰色折叠工具记录和独立确认卡；修改按连接展开，主助手可在桌面停靠/浮窗切换，Skills内部标识折叠、时间转为北京时间。已有Vite服务刷新即可，无新增后端或迁移要求。见[交付](../../docs/apps/web/changelog/2026-10-19-interface-polish.md)。

项目树初次默认收起，切换目录保留展开/滚动，当前选中项自动可见；深层链接只展开所需祖先。刷新Web即可，见[目录交互记录](../../docs/apps/web/changelog/2026-10-19-project-tree-navigation.md)。

答案对比按用户反馈简化为上方提取结果、下方标准答案，图纸页跟随左侧目录；表内独立滚动/分页，横向同步。说明/统计/筛选和匹配状态已移除，导入/更换在标准答案标题右侧图标。见[当前展示](../../docs/apps/web/changelog/2026-10-19-stacked-answer-comparison.md)。

临时答案核对：对应项目→“答案对比”→“导入答案 XLSX”。1002001641 PERU TPP 1 STS选择本地1641.xlsx，按业务页查看完整提取结果与字段差异。答案只存浏览器内存、按项目隔离，刷新或退出后重导，不上传/写库。新环境先corepack pnpm install，现有环境刷新Web即可，无后端重启/迁移；见[交付](../../docs/apps/web/changelog/2026-10-19-temporary-answer-comparison.md)。

2026-10-19右下角全局主助手已接通持久会话、业务导航、专业Agent及真实差异卡。需加载8000 API2.11.0和新版8100后刷新Web；附件先暂存，发送/Enter才提交。123项模拟浏览器回归通过，未调用真实模型。见[交付](../../docs/apps/web/changelog/2026-10-19-main-assistant.md)。

2026-10-19上传PDF规则选项和Extraction Skills统一读取数据库中已上传资源包，不再从本地目录登记或补齐；查看规则读取对应Storage ZIP。当前ZH2.3.0/ABB1.3.1/XMZ0.2.1已上传，重载8000并刷新页面生效，见[交付](../../docs/apps/web/changelog/2026-10-19-database-profile-options.md)。

全量重扫预览显示将删除/写入的全部范围，确认后一次性替换；局部只修订选中行/字段。空结果明确提示删空，旧候选不能确认，新行ID替换后追问自动切到所属页新结果。需本地新迁移（已装）、8000 API2.10.0与8100/实际Worker新代码，再刷新页面并新建重扫。见[交付](../../docs/apps/web/changelog/2026-10-19-rescan-scope-replacement.md)。

系统已改名“振华重工放线表提取系统”。选择项目根目录时可导出全部当前正式线表为13列XLSX；Explain标题栏支持拖动/方向键/Home，普通打开不展示项目旧重扫任务，需点击历史按钮查看。普通自动解释禁用重扫工具，主动需求和重扫按钮保留。需重载8000 API2.9.0及8100，再刷新前端；无新迁移，提取Worker不需因本轮改动重启。见[交付](../../docs/apps/web/changelog/2026-10-18-project-export-chat.md)。

图纸预览现支持滚轮缩放、按住中键拖动，项目标题旁可收起/展开目录。工具栏重扫自动发送当前范围请求；聊天图片在所属回复中展示，点击可居中放大、Esc关闭。候选确认保存保持。已有Vite服务刷新即可，无新后端或迁移要求，启动命令不变。见[交付](../../docs/apps/web/changelog/2026-10-18-workbench-interactions.md)。

Explain现在支持粘贴/拖拽/上传细节图、选择所属原页/关联页、自然语言发起重扫、进度/取消与候选逐行确认。原图/关联图仍用于定位，确认前表格保持原值，成功后刷新并保留记录所属页。需8000 API2.8.0、8100及现有Worker新代码，以及`20261018050000`迁移；前端仍按下方Vite命令启动，已有开发服务刷新即可。见[交付](../../docs/apps/web/changelog/2026-10-18-explain-rescan.md)。

Explain修改确认修复需API2.7.1/8100新代码：当模型只口述预览而未调用工具，服务端撤回未验证文字并尝试生成真实方案；前端处理answer_reset，实际方案到达后才显示确认按钮，输入“确认”不直接写库。无数据库迁移，刷新前端并重发原修改请求。见[记录](../../docs/service/agent/changelog/2026-10-18-explain-preview-receipt.md)。

Explain浮窗支持按工作区/原理号提出线表修改：先回答，再展示逐行对照，确认/拒绝后反馈；支持端子去前缀、整组起终点交换及字段修正。确认后自动刷新表格，后续追问使用新行版本。需API2.7.0/8100新代码；[新增迁移](../../supabase/migrations/20261018020000_explain_connection_edits.sql)已在本项目本地部署，其他环境需应用。前端启动参数不变，未改真实线表。见[交付](../../docs/apps/web/changelog/2026-10-18-explain-edit-preview.md)。

查看规则现在支持双击内容编辑和旁侧Profile Agent辅助编辑，可上传图纸、填写实际提取结果、展开工具及建议diff，用户同意后应用并发布替换新版。需加载8000 API2.6.0和8100新代码；前端沿用Vite启动方式，无新增环境变量。见[交付](../../docs/apps/web/changelog/2026-10-18-profile-rule-editing.md)。

规则聊天失败现在会显示具体模型错误码和诊断编号，支持同轮重试；需重载8100启用对应日志/诊断，见[失败态记录](../../docs/apps/web/changelog/2026-10-17-profile-model-errors.md)。

2026-10-17规则聊天第一阶段新增[PDF随机两页抽样](../../docs/apps/web/changelog/2026-10-17-profile-pdf-sampling.md)：上传PDF后自动对照两页推测分页，每页独立Expected；只保留选中样图，原PDF和其余页不缓存。后两阶段继续人工上传图片。单页/失败重试/来源页说明可见，使用前重新加载8000 API2.5.0和8100，本轮无新迁移。

2026-10-17规则配置智能体现默认使用[引导式聊天](../../docs/apps/web/changelog/2026-10-17-profile-conversation.md)：先输入名称，再发送说明或上传/粘贴图片；Agent逐步追问并展示三个阶段读图结果，确认后保存规则与Expected，最后手动发布。刷新可选草稿恢复对话，原表单兼容入口为`/agents/profile?editor=form`。使用新链路需加载8000 API2.4.0及8100新代码，沿用现有启动命令，本轮无新增迁移。

智能体中心→规则配置智能体已接入三步创建向导：上传样图/负例、描述拆分/提取/补全规则、生成并编辑Expected表格、逐步确认、手动发布；草稿刷新可恢复。未保存修改会阻止发布，前序确认变化使后续阶段失效。沿用当前前端启动命令；使用新功能前需加载8000/8100与Worker新代码，并应用[发布迁移](../../supabase/migrations/20261017010000_profile_wizard_publication.sql)。规则诊断/聊天编辑入口仍后续接入。

图纸预览模式支持拖动线表与图纸间的分隔条调整宽度，也可用方向键/Home/End调节、双击恢复等宽；切换模式保留本次比例，刷新恢复默认。缩放百分比完整显示，点击恢复100%，长标题悬停查看全文。窄屏继续上下展示。见[交付记录](../../docs/apps/web/changelog/2026-10-17-preview-resize.md)。

2026-10-17工作台改为全量线表/图纸预览双模式：默认填满中间区域、不显示线号及底部图纸；预览时保留五列并在右侧上下显示原页/目标页，按端点独立PDF物理页标注坐标。用户菜单“智能体中心”展示三Agent，提取规则迁入Extraction下的zh_extraction等Skills；Skill版本真实读取，Agent独立版本/在线健康未提供时如实标明。44项浏览器及前端检查通过，仅前端修改，后端无需重启。见[交付](../../docs/apps/web/changelog/2026-10-17-agent-center-preview.md)。

2026-10-17项目名可在侧栏/当前项目标题双击原地修改，Enter或失焦保存、Esc取消，失败保留输入；工作区暂不提供改名。目录与图纸按原编号自然升序展示，图纸主标签简化为006M01等编号，PDF页号保持。32项浏览器与前端检查通过，仅前端修改，无需重启后端。见[交付](../../docs/apps/web/changelog/2026-10-17-project-tree-inline.md)。

2026-10-17来源解释增加前端逐字缓冲与Markdown渲染，整段/缓存/完成事件也逐步显示；可立即显示已收到内容，停止冻结可见文字，减少动态效果时直接显示。浮窗与Markdown按需加载，26项浏览器和前端检查通过。仅前端修改，无需重启8000/8100；刷新后打开新解释即可。见[交付](../../docs/apps/web/changelog/2026-10-17-explain-typewriter.md)。

2026-10-17接入独立来源解释浮窗：悬停起点端子显示行解释入口，悬停组首页码显示整页入口；触屏直接显示按钮。点击自动解释，可追问、停止或重试，工具记录用淡色文字折叠展示，提供原页/跨页图纸。新浮窗独立于现有主助手，不改提取或线表。浏览器仅请求8000，需加载新版API并启动[8100共享宿主](../../services/agent/README.md)。见[交付](../../docs/apps/web/changelog/2026-10-17-explain-panel.md)。

2026-10-16新增上传即提取与实时结果展示：阶段等待状态、渐进目录、初扫行、补全更新、复核原因及失败重试。前端只请求8000，通过JWT SSE通知补读数据库快照；处理中的结果只读。启动命令不变，使用前需应用新增迁移并启动[新Worker](../../services/agent/README.md#当前增量提取的启动方式)。AI聊天仍未开放。见[Web交付](../../docs/apps/web/changelog/2026-10-16-incremental-extraction.md)。下文较早上传仅保存的说明为历史记录。

登录后直接进入工作区：有项目默认打开首个项目，无项目显示完整空工作区并可上传/登记规则。重命名和删除在左侧项目树，独立项目目录页已取消。见[入口记录](../../docs/apps/web/changelog/2026-10-16-workspace-entry.md)。

2026-10-16当前为三表数据管理界面：选择规则后保存PDF、项目/JSON图纸目录、批次线表/行级CRUD与规则引用预览。上传不会启动Agent，AI输入明确未接入。刷新前需重启8000后端加载新接口；详见[交付](../../docs/apps/web/changelog/2026-10-16-simple-management.md)。下文旧聊天/规则发布说明仅为历史记录。

2026-10-13 聊天微调：主面板改为“电气图纸与线表智能助手”，日常回复通过 SSE 累积到同一条对话，不显示确认卡片或刷新线表；任务说明逐字显示完后才呈现后续任务/确认卡片。上传提示使用 Stage 1/2 提取路线，流中断保留已收到文字并停止光标。详见[记录](../../docs/apps/web/changelog/2026-10-13-supervisor-chat.md)。

线表智能提取系统的新前端，使用 React + Vite + TypeScript。当前默认读取真实 Server 数据，不依赖旧 `frontend/`。旧 Mock 资产保留但不参与运行。

## 目录结构

```text
apps/web/
├─ public/                 # 原样发布的静态文件
├─ src/
│  ├─ apis/                # HTTP Client、接口函数、DTO 和 Mock 适配器
│  ├─ assets/              # 全局样式和打包资源
│  ├─ components/          # 可复用业务组件
│  ├─ directives/          # 预留的底层 DOM 行为适配器
│  ├─ hooks/               # 可复用交互逻辑
│  ├─ layout/              # 路由布局
│  ├─ router/              # React Router 路由和后续守卫
│  ├─ stores/              # 跨页面状态
│  ├─ views/               # 路由页面
│  ├─ App.tsx
│  └─ main.tsx
├─ .env.example
├─ index.html
├─ package.json
├─ tsconfig.json
└─ vite.config.ts
```

## 路由

```text
/login
/projects
/projects/:projectId
```

项目页包含 Header、顶部资源导航（线表工作区 / 图纸库 / 规则库）、`项目 -> 工作区 -> 图纸` 树、结构化线表、图纸证据，以及 Supervisor 主 Agent 运行监工区。

上传 PDF 后自动创建真实项目并向 Agent 请求识别；类型确认后运行三阶段，Stage 1 发布后从 Server 刷新图纸树。右侧显示真实公开计划/诊断依据和阶段卡片；数据修订与规则候选均保留人工确认。新任务可重置短期会话，浏览器刷新可重新订阅原 run；Agent 重启后的短期会话不可恢复。

每阶段卡片原位更新，最终类型确认提示可见；进度断线按序号自动续传，也可点击“重新连接进度”，不会重新提交任务。图纸链接过期可刷新；编辑电压/端子排会影响同线号的所有记录，失败重试复用同一提交键。

规则库可点击“新建规则包”，选择已发布模板，填写唯一规则标识/名称/识别说明与特征，可展开编辑三阶段 Prompt，勾选确认后创建并注册。图片 Few-shot、expected JSON、Schema 和算法继承模板；当前只支持已实现的 ZH adapter。创建者有删除按钮，确认后停用并刷新列表，历史项目保留原包。已有 key 的规则改动继续走候选评测/审核/发布。

本次规则包功能的应用 strict 类型检查和 7 项浏览器夹具通过；本机 node_modules 文件读取 EPERM 阻塞 lint、production build 和 OpenAPI 自动生成。API 快照已导出，客户端新契约暂手动同步；权限修复后需重新生成并执行完整检查，见[实施记录](../../docs/service/server/changelog/2026-10-12-rule-package-lifecycle.md)。

## API 模式

需要本地覆盖配置时，将 `.env.example` 复制为 `.env.local`：

```env
VITE_API_BASE_URL=
```

开发环境默认同源 `/api`，Vite 转发到 8000，避免 localhost/127.0.0.1 混用导致 refresh cookie 丢失。生产部署同源反向代理 `/api` 到 Server。前端不得配置内部 Agent Token 或 Supabase service-role。

先启动 [Server](../../services/server/README.md) 和 Agent，再启动 Web。使用已有 Supabase 用户的邮箱/密码登录；用户 UUID 不能代替登录。无需把模型或数据库密钥放入浏览器。

线表工具栏“新增端子”将端子加入已有线号，指定来源页及可选跨页目标；行内删除需确认。操作保留其他 ID/线号并刷新结果。增删需要 Server PostgreSQL 事务连接；本地使用 Server README 中的 `run_local_api.py`，无连接返回 503，不绕过审计。

## 启动

以下命令使用 Windows PowerShell。首次安装需要 Node.js 和 Corepack；所有命令从仓库根目录执行，克隆路径不同时调整 `Set-Location`。完整本地联调按 Agent → Server → Web 的顺序启动，每个服务使用独立终端。

首次安装依赖（已有依赖时跳过）：

```powershell
Set-Location E:\project\zhenghua_test
corepack pnpm install
if (-not (Test-Path apps\web\.env.local)) { Copy-Item apps\web\.env.example apps\web\.env.local }
```

启动前端开发服务：

```powershell
Set-Location E:\project\zhenghua_test
corepack pnpm dev:web
```

访问 `http://127.0.0.1:5174`，登录页为 `/login`。`VITE_API_BASE_URL` 默认留空，`/api` 由 Vite 代理到 `http://127.0.0.1:8000`；后端启动见 [Server README](../../services/server/README.md)，AI 服务启动见 [Agent README](../../services/agent/README.md#启动)。端口被占用时 Vite 会报错，不会自动切换端口；开发服务可在所属终端按 `Ctrl+C` 停止。

质量检查：

```powershell
corepack pnpm typecheck:web
corepack pnpm lint:web
corepack pnpm build:web
```

浏览器回归：`corepack pnpm --filter @wiring/web exec playwright test`。使用显式HTTP夹具、本地Chrome和独立5186端口，截图存于忽略的`.runtime/simple-management-browser`，不调用模型。旧业务表/Agent合约留在tests/legacy-workbench.fixture.ts，不计入当前回归。生成接口类型：先执行`apps/api/scripts/export_openapi.py`，再执行`openapi-typescript ../api/openapi.json -o src/apis/generated.ts`。

旧 Vite 前端继续使用 `5173`，新前端使用 `5174`，迁移期间可以同时运行。

## GCR101 关联项目演示

选择 `1002001693大车卷盘图纸 → GCR.1 → GCR101`，点击“答案对比”旁的“关联项目”。图谱显示低压配电系统与照明配电系统，支持按0261/0262/0263查看端子对、点击项目/图纸跳转及返回GCR101。项目目录的Mock文件夹也可直接打开两个模拟项目。

数据在 `src/apis/mock/project-relations.ts`，仅前端只读展示；模拟项目/页码不代表已核验关联，不会向业务API登记或提交。只有目录中存在大车卷盘来源项目时才展示Mock目录。刷新Web即可使用，无后端/数据库部署步骤。

验证：`node node_modules/@playwright/test/cli.js test tests/project-relations.spec.ts tests/simple-management.spec.ts tests/answer-comparison.spec.ts --workers=2`。交付见[关联演示](../../docs/apps/web/changelog/2026-10-20-project-relations-mock.md)。
