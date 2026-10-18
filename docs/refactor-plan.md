# 线表智能提取系统重构方案

> 状态：Draft for review  
> 日期：2026-10-09  
> 目标技术栈：React + Vite + TypeScript、FastAPI + Python、LangGraph、Supabase、PostgreSQL

## 1. 重构结论

2026-10-18项目全量XLSX二进制导出及Explain按需重扫历史契约见[ADR-0035](./adr/0035-project-xlsx-export.md)：Server固定批次和版本核对，普通自动解释禁用重扫工具，拖动和项目级入口属于Web。

2026-10-18 Explain重扫实施设计见[ADR-0034](./adr/0034-explain-rescan.md)：私有辅助图+原图/关联图、原Profile冻结、复用Stage2及候选隔离持久化、租约Worker和确认后原子ResultPatch，已有记录归属固定。

2026-10-18 Explain线表修改设计见[ADR-0033](./adr/0033-explain-connection-edit-tools.md)：模型产生强类型精确范围proposal，用户查看逐行对照后经Server事务确认；整组端点/坐标对象调换，记录所属页、工作区及关联跨页索引固定，坐标内部PDF页号随端点保留。此前迁页约定已纠正，见[修正](./service/server/explain-swap-origin-correction.md)。

2026-10-18基于Profile Agent扩展现有规则编辑：预览双击手动修改及旁侧工具聊天，可信包派生草稿，建议确认后发布替换新版与引用感知旧包回收，见[ADR-0032](./adr/0032-profile-resource-editing.md)。

2026-10-17 ZH局部补全2.2.1在适配器默认值前检查无内容响应，使用已有两次校验重试并在失败后继续；N线按来源页与完整信号名匹配。保持Graph拓扑/状态枚举和坐标契约，设计见[计划](./service/agent/zh-completion-response-plan.md)。

2026-10-17 Profile补全聊天允许受控返回初扫生成修正候选，解决同页误判后仍反复索要目标图；保持显式确认与依赖失效，见[ADR-0031](./adr/0031-profile-scan-correction.md)。

2026-10-17 Profile分类聊天增加PDF随机两页抽样：只渲染选中页并保留草稿证据，原PDF及其余页不落盘，后两阶段仍由用户提供图片。见[ADR-0030](./adr/0030-profile-pdf-sampling.md)。

2026-10-17 Profile规则创建将迁移为Agent引导的多轮聊天，复用三阶段候选/确认及发布，新增持久对话与SSE；见[ADR-0029](./adr/0029-profile-conversation.md)。

2026-10-17 Profile 三步向导和手动发布实施中，见 [ADR-0028](./adr/0028-profile-creation-publication.md)：阶段候选与人工确认分离，私有固定版本规则包接通目录、预览和提取 Worker；原本地规则兼容。

2026-10-17前端智能体中心/提取Skills及双模式校验工作台见[ADR-0027](./adr/0027-agent-center-and-preview-workbench.md)：用户菜单集中Agent与规则入口，线表按需压缩并在右侧显示原/目标图及端点坐标。本轮只改前端，不改变Profile key、API/数据库或提取顺序；Agent运行元数据缺口明确说明。

2026-10-17独立Profile Agent方案见[ADR-0026](./adr/0026-independent-profile-agent.md)：复用固定提取Schema，以可配置模板填充规则及图像案例，基于证据诊断，确认或明确指令后编辑隔离草稿并输出可验证规则包。本轮不接界面/正式发布，不修改并行Explain实现。

2026-10-17 Explain已通过8000 JWT代理接入8100共享宿主，新增独立前端来源浮窗、行/页入口与工具结果/图纸流；公共DTO从Agent生成Server适配器再生成TS，不让Server导入Agent执行代码。代码与离线验收完成，未重启实际服务；见[ADR-0025](./adr/0025-explain-panel-integration.md)。

2026-10-16 Explain从固定行解释扩展为行/页精确检索工具循环：search_connections读取线表及关联图纸，view_drawings按需提供图像；前端选择与身份/项目边界分离，查询/图片摘要每轮刷新，分页覆盖显式返回。独立模块已离线验证，未接前端或共享服务；见[ADR-0024](./adr/0024-explain-retrieval-tools.md)。

2026-10-16 独立Explain Agent实施设计见[ADR-0023](./adr/0023-independent-explain-agent.md)：按可信身份只读三表行记录和图纸证据，LangGraph生成公开解释及多轮回答；不接旧Supervisor、不改提取或业务数据，缺失历史证据明确说明。

2026-10-16 提取复核改为统一后处理：VLM报告事实/不确定性，程序输出复核标志、原因和阶段状态，待补全与最终缺失分别处理；设计见[复核计划](./service/agent/extraction-review-plan.md)。用户已确认同时实施上传即提取、逐步写库和前端实时展示，见[ADR 0022](./adr/0022-incremental-extraction.md)；不执行此前待确认的旧Agent清理。

2026-10-16 用户授权清理旧Supervisor/纠错/自完善等失效控制面，先独立开发extraction/explain/profile能力，未来再统一主Deep Agent；共享服务保留最小探活/本地规则只读能力，不启用旧业务表任务链路。见 [ADR-0021](./adr/0021-independent-agents-before-orchestration.md)。

2026-10-16结果表新增可空起终点JSONB坐标，API/前端类型沿用Agent的x/y归一化点及所属PDF物理页，端点变更清理旧坐标；图片高亮及Agent落库仍后续接入。见[坐标契约](./service/server/terminal-coordinate-contract.md)。

2026-10-16前后端三表数据管理已完成：API v2的batch_id/record_version、项目JSON图纸索引和事务行级RPC；上传仅保存，Agent入口禁用待接入。14项后端、10项浏览器和真实本地Auth/Storage/CRUD验收通过，详见[ADR-0020](./adr/0020-three-table-management-contract.md)及[交付](./service/server/changelog/2026-10-16-simple-management.md)。

2026-10-16本地ZH2.1.1补全上下文v2只传来源匹配事实与元件元数据，起点端子/坐标/方向留在state；不限制目标回指箭头朝向，沿线分别读接口与针脚。不可定位地址只以唯一来源页PDF引用核对，新增可选source_index_raw保留依据。Graph拓扑和14列表格不变，见[方案](./service/agent/zh-cross-page-reading-fix-plan.md)。

2026-10-16用户确认先将前后端数据管理适配三表，Agent上传后提取/落库后续再改。本轮使用批次与行版本契约、项目JSON图纸索引，上传只登记并保存文件；见[接入计划](./service/server/simple-schema-management-plan.md)。

2026-10-15本地ZH2.1.0采用目标图加初扫来源事实完成定向连接；公共Graph由Profile输入模式控制是否加载来源图，默认双图保持ABB/XMZ及旧包兼容，不改变阶段拓扑。内部增加可选signal_name及版本化上下文，业务页匹配与图片物理页坐标分离。见[设计](./service/agent/zh-target-only-completion-plan.md)。

2026-10-15公共图像传输策略改为输入图优先分配像素，案例先压缩/整组减少，输入自身超预算才继续缩小；无模板条件分支，原图及坐标含义不变。设计见[预算方案](./service/agent/model-image-budget-plan.md)，实现/未验收项见[记录](./service/agent/changelog/2026-10-15-input-first-image-budget.md)。

2026-10-15用户要求所有模板主表对齐ZH14列，并补齐ABB/XMZ端子坐标说明/图像expected；公共Graph与CLI共用表头/行映射，固定导入模板保留独立格式。见[ADR-0019](./adr/0019-unified-extraction-table.md)，不重跑模型或覆盖旧结果。

2026-10-15本地ABB1.1.3按用户确认修订为小圆圈放线、大圆圈端子，同段双标记一条连接，原理号数字或完整端子直接拼来源Sheet；跨页/Sheet.列行保持独立。设计与静态验收边界见[修订记录](./service/agent/abb-circle-rule-update.md)，未运行测试/模型或发布。

2026-10-15本地ZH2.0.4以003C01替换旧接收/跨页样例，端点增加归一化坐标及本端图片物理页，最终记录/本地14列XLSX保留；坐标不影响连接身份，补全不改来源坐标。契约见[ADR-0016](./adr/0016-zh-direct-terminal-segments.md)，静态核对与未验收项见[记录](./service/agent/changelog/2026-10-15-zh-c01-terminal-coordinates.md)。

2026-10-14本地ZH2.0.3明确元件标识优先级与Object Loc回退；内部补全仅可完善来源元件元数据，起点端子和原理号保持。数据含义修订见[ADR-0016](./adr/0016-zh-direct-terminal-segments.md)与[记录](./service/agent/changelog/2026-10-14-zh-component-priority.md)，未运行真实模型或发布。

2026-10-14用户随后明确放弃旧业务数据并授权直接删除：本地已创建三张精简业务表并删除18张旧表/1个视图，Agent/Auth/Storage数据保留；属于用户对渐进保留旧schema原则的明确例外。当前应用仍待适配，详见[ADR-0018](./adr/0018-simple-extraction-business-tables.md)和[部署记录](./service/server/changelog/2026-10-14-local-business-table-retirement.md)。

2026-10-14按用户要求提供三张精简提取业务表的新增SQL草案，现有应用/数据仍使用旧schema；仅交付创建指令，不执行迁移或删除。设计及接入限制见[ADR-0018](./adr/0018-simple-extraction-business-tables.md)。

2026-10-14按用户新布局迁移独立提取实现到`services/agent/src/agent/extraction_agent`，共享控制面保留，算法不变只调整引用；见[ADR-0017](./adr/0017-extraction-agent-directory.md)。原模板资源路径由该目录接管。

2026-10-14 ZH用户口径修订见[ADR-0016](./adr/0016-zh-direct-terminal-segments.md)：按放线标记读取两侧直接端子、遇端子停止；导出端子排由程序映射，VLM只读实际端子。保留Stage2逐页工作流及电流约束，精简其他硬提示，本地版本2.0.2，不写库或发布。

2026-10-13 Supervisor 对话微调设计见 [对话计划](./service/agent/supervisor-chat-plan.md)：日常聊天直接流式回答，任务说明后才显示卡片，完整提取仍要求会话内真实 PDF 与类型确认；现有任务权限/持久化边界保持不变。

2026-10-13 本地新增 ZH 大车卷盘网格页标 experimental Profile，采用独立页标/引用策略及可逆接口映射，不上传或修改生产资源；见 [ADR-0015](./adr/0015-zh-gantry-reel-profile.md)。

2026-10-13 提取链路调整实施见 [ADR-0014](./adr/0014-stage2-page-extraction-workflow.md)：Stage 2 独立逐页 LangGraph 内部执行扫描、双图定向补全与完成页持久化，新运行取消独立 Stage 3；历史兼容和最终业务版本边界见 ADR。

2026-10-13 规则变更契约由用户调整：[ADR-0013](./adr/0013-confirmed-rule-update-without-evaluation.md) 替代下文历史方案中的评测/审核门禁。当前链路为归因建议→一次用户确认→构建并直接启用不可变规则版本。新增受控 RPC 原子启用包/候选并留确认审计，不伪造评测报告；保留旧项目版本和并发/权限/完整性校验。旧评测实现只兼容已入队任务，停止新评测启动。

采用渐进式 monorepo 重构，不重写已经验证过的 PDF 渲染和 LangGraph 提取代码。第一阶段先建立新目录、数据库领域模型、认证和项目树；随后将现有 Agent 包装为独立 Worker，并按图纸 Profile 拆出振华、ABB 等模板规则。

核心变化：

- 前端在 `apps/web` 重建为模块化 React + Vite + TypeScript 应用，旧 `frontend/` 保留为迁移期兼容实现；
- `frontend/public/library` 从业务数据源降级为迁移期兼容产物；
- 数据库从单张 `wiring_tables` JSONB 表升级为项目化、可查询、可审计模型；
- FastAPI 从“文件处理接口”改为领域 API，并通过独立 Worker 执行长任务；
- Agent 从振华专用逻辑改为“稳定公共流程 + 可版本化图纸 Profile”；
- XLSX 是派生产物，数据库中的结果版本才是事实来源；
- 用户反馈不会直接改生产 Prompt，而是进入可测试、可审核的规则演进流程。

## 2. 现状与问题

当前原型已经具备：

- PDF 上传、约 300 DPI 拆页；
- 页面分类、当前页扫描、跨页补全；
- Prompt 图片 Few-shot；
- JSON/XLSX 输出、断点文件和测试脚本；
- Supabase Storage 上传和 `wiring_tables` 落库；
- Vite 管理页原型。

主要限制：

1. `job/group/records` 混在一张表中，项目、工作区、图纸没有独立身份。
2. 页面图片和 checkpoint 写在前端 `public` 目录，运行时写入与前端监听冲突。
3. 前端直接聚合 JSONB，无法稳定做分页、检索、权限和行级修订。
4. FastAPI `BackgroundTasks` 不适合小时级任务、进程重启和多 Worker。
5. 默认 Prompt 路径与振华模板绑定，ABB 等模板容易通过条件分支污染公共流程。
6. 缺少用户、权限、结果版本、反馈审计和规则发布机制。

## 3. 目标架构

```mermaid
flowchart LR
    U["用户"] --> W["React + Vite Web"]
    W --> A["FastAPI Domain API"]
    W --> SA["Supabase Auth"]
    A --> DB["PostgreSQL / Supabase"]
    A --> ST["Supabase Storage"]
    A --> AG["Agent API :8100"]
    AG --> Q["Agent Queue"]
    Q --> WK["Python Agent Worker"]
    WK --> LG["LangGraph Workflow"]
    LG --> PF["Drawing Profiles: ZH / ABB / ..."]
    LG --> VLM["OpenAI-compatible VLM"]
    WK --> DB
    WK --> ST
    DB --> SSE["Run Events / SSE"]
    SSE --> W
```

### 3.1 边界原则

- Web 只负责交互和展示，不持有 service-role key，不执行业务写入。
- API 负责鉴权、领域规则、事务、签名 URL、导出和任务编排。
- 独立 Agent API 使用 `8100` 端口接收异步 run；Worker 负责耗时处理、checkpoint、阶段事件和结果 proposal。
- Graph 只编排稳定阶段，不包含某家图纸的硬编码规则。
- Profile 封装模板识别、Prompt、Few-shot、引用解析、字段策略和校验器。
- PostgreSQL 保存结构化事实；Storage 保存 PDF、图片和阶段产物。完整提取通过受控 RPC 创建结果代次；局部修订由用户确认后通过独立受控 RPC 原位更新当前记录并保存 before/after 审计，连接 ID/线号不变、revision 递增，旧代次不改。`apps/api` 接入后承担外部鉴权入口。详见 ADR-0010。

## 4. Monorepo 目录

目标目录如下，迁移期间旧 `frontend/` 和 `backend/` 暂时保留：

```text
zhenghua/
├─ apps/
│  ├─ web/                         # React + Vite + TypeScript
│  │  ├─ src/apis/                 # API Client、接口函数和 DTO
│  │  ├─ src/assets/               # 样式和静态资源
│  │  ├─ src/components/           # 可复用业务组件
│  │  ├─ src/hooks/                # 复用交互逻辑
│  │  ├─ src/layout/               # 应用布局
│  │  ├─ src/router/               # 路由与守卫
│  │  ├─ src/stores/               # 跨页面状态
│  │  └─ src/views/                # 路由页面
│  └─ api/                         # FastAPI
│     └─ src/
│        ├─ modules/               # auth/projects/workspaces/drawings/runs/wiring/feedback
│        ├─ infrastructure/        # db/storage/queue/vlm adapters
│        └─ main.py
├─ services/
│  ├─ agent/
│  │  ├─ src/
│  │  │  ├─ graph/                 # LangGraph 公共拓扑和 state
│  │  │  ├─ runtime/               # checkpoint/events/retry/idempotency
│  │  │  ├─ profiles/              # profile registry 和协议
│  │  │  └─ validation/            # 公共确定性校验
│  │  ├─ profiles/                 # ZH / ABB / 后续模板版本包
│  │  └─ tests/                    # contract / graph / profile regression
│  └─ server/                      # 领域服务、repository 与基础设施适配器
├─ packages/
│  ├─ ui/                          # 共享 UI 与设计 tokens
│  ├─ api-client/                  # OpenAPI 生成的 TS Client
│  └─ config/                      # ESLint/TS/Tailwind 等共享配置
├─ infra/
│  └─ supabase/                    # migrations、seed、RLS
├─ docs/
├─ scripts/
├─ pnpm-workspace.yaml
├─ pyproject.toml
└─ turbo.json
```

建议使用 `pnpm workspace + Turborepo` 管理 TypeScript 包，Python 使用 `pyproject.toml + uv`。OpenAPI 是前后端接口契约来源，禁止手写两套不一致的 DTO。

## 5. 领域模型与数据库

### 5.1 核心实体

| 实体 | 作用 | 关键字段 |
| --- | --- | --- |
| `profiles` | 用户资料 | `id -> auth.users.id`, `display_name`, `avatar_url` |
| `projects` | 一次 PDF 上传形成的项目 | `owner_id`, `name`, `standard_profile`, `status` |
| `project_members` | 项目权限 | `project_id`, `user_id`, `role` |
| `document_files` | 原始 PDF 与对象存储记录 | `project_id`, `storage_path`, `checksum`, `mime_type` |
| `workspaces` | 项目内工作区 | `project_id`, `code`, `name`, `sort_order` |
| `drawings` | 工作区内图纸页 | `workspace_id`, `pdf_page`, `drawing_page`, `image_path`, `status` |
| `extraction_runs` | 一次可恢复处理运行 | `project_id`, `profile_version`, `status`, `current_stage` |
| `extraction_events` | 阶段事件流 | `run_id`, `seq`, `stage`, `level`, `payload` |
| `wiring_units` | 一个结果版本内的端子排逻辑单元；数据库从 1000 分配线号 | `result_version_id`, `workspace_id`, `drawing_id`, `wire_number`, `voltage_level`, `terminal_strip`, `status` |
| `wiring_connections` | 端子排下的一条芯线/端子明细 | `unit_id`, `principle_number`, `start_code`, `start_description`, `start_terminal`, `end_code`, `end_description`, `end_terminal`, `current_value`, `remark`, `color_mark` |
| `connection_evidence` | 来源与定位证据 | `connection_id`, `drawing_id`, `kind`, `bbox`, `raw_text` |
| `result_versions` | 可导出结果快照 | `project_id`, `run_id`, `version`, `created_by` |
| `feedback_items` | 用户修订与规则建议 | `scope_type`, `scope_id`, `before`, `after`, `status` |
| `profile_versions` | Agent Profile 发布记录 | `profile_key`, `version`, `checksum`, `status` |

### 5.2 数据约束

人工单条端子增删按 [ADR-0011](./adr/0011-manual-connection-insert-delete.md) 实施：Server 既有表事务、稳定其他记录/线号、完整删除前证据审计和 revision/幂等；不新增数据库 Schema 或修改 Agent 核心。

- `projects.owner_id`、成员关系和所有读取接口必须受 RLS/后端鉴权保护。
- `drawings` 同时保存 PDF 物理页号和图纸业务页号，二者不得混用。
- `wiring_connections` 保存可查询列；VLM 原始响应放 `raw_payload jsonb`，不能只存整包 JSON。
- 一个 `wiring_unit` 对应一个端子排和一个线号，可包含多条 `wiring_connections`；线号由数据库在结果版本内从 `1000` 事务安全递增，不由 Agent 猜测。
- 项目名称、工作区名称和工作区业务页码通过规范化外键维护，并由扁平只读视图提供给 Agent/API 检索；业务页码使用文本，PDF 物理页号单独保存。
- 每条连接必须关联至少一条来源证据，人工录入例外需显式标记来源类型。
- 用户修订使用新版本或审计记录，不直接覆盖且不留痕。
- 旧 `wiring_tables` 在迁移期只读，完成数据回填后删除。

### 5.3 Storage 路径

Bucket 默认改为私有，前端通过短期签名 URL 访问：

```text
projects/{project_id}/original.pdf
projects/{project_id}/workspaces/{workspace_id}/drawings/{drawing_id}.png
projects/{project_id}/runs/{run_id}/stage-1/classification.json
projects/{project_id}/runs/{run_id}/stage-2/page-scan.json
projects/{project_id}/runs/{run_id}/stage-3/cross-page.json
projects/{project_id}/runs/{run_id}/exports/wiring-table.xlsx
```

对象路径只使用不可变 UUID，不使用可改名或可能重复的项目/工作区名称。前端通过数据库中的项目名、工作区名和图纸业务页码展示树形结构，并通过短期签名 URL 读取私有对象。

Checkpoint 写入 Worker 本地 runtime 或专用对象路径，不再写入 Web 的静态目录。

## 6. 前端方案

### 6.1 路由

```text
/login
/projects
/projects/[projectId]
/projects/[projectId]/workspaces/[workspaceId]
/projects/[projectId]/drawings/[drawingId]
/projects/[projectId]/runs/[runId]
```

### 6.2 项目工作台

2026-10-13 展示更新：真实工作台改为左侧导航+中间业务内容两列，Supervisor 聊天移入右下角按钮控制的悬浮窗口；图纸库为项目→工作区→图片原地展开与预览。下面三栏描述保留为早期方案，当前实现以 [前端更新计划](./apps/web/floating-chat-plan.md) 为准。

采用稳定三栏布局：

- Header：品牌、项目切换、运行状态、用户菜单；
- 左侧 280px：项目、工作区、图纸树，支持折叠、状态点和搜索；
- 项目顶部导航：线表工作区、图纸库、规则库；操作区提供 PDF 上传与结果导出；
- 中间 `minmax(0, 1fr)`：结果表格为主，图纸预览和处理过程用 Tabs；
- 跨页引用终点可以悬浮高亮，点击切换到目标图纸并定位目标端子；非跨页终点保持静态；
- 右侧 320px：Supervisor 主 Agent 监工区。初始为空；用户显式开启 Mock 模拟链路并上传 PDF 或提交自然语言需求后，按事件流淡化输出主 Agent 思考，依次显示加粗的 Agent 调度、处理中等待标记、完成勾选、工具结果与错误。模拟仅用于前端演练，不伪装成真实 Agent 运行。

中间区域默认显示线表，不制作营销式首页。表格使用虚拟滚动或服务端分页；固定表头，列宽可调整，点击来源页打开图纸预览。PDF 上传后先登记源文件；Stage 1 完成后才在树中呈现工作区和拆分页，再依次推进后续 Agent。阶段状态由右侧事件流呈现，不重复添加顶部 Validation 进度条。Mock 阶段允许本地事件流和结构化结果 patch；连接后端后切换 API adapter，生产事件仍以数据库和持久化 run 为准。

### 6.3 状态管理

- 服务端数据：TanStack Query；
- 页面状态：URL search params；
- 短期 UI 状态：React state；
- 表单：React Hook Form + Zod；
- 组件：自建薄组件层，可基于 Radix primitives；
- 图标：Lucide；
- 鉴权：Supabase Auth，React Router 路由守卫保护页面，FastAPI 校验 JWT。

### 6.4 事件流

`GET /api/v1/runs/{run_id}/events` 提供 SSE。前端根据事件更新阶段和 Supervisor 监工面板，不再每 2.5 秒重新拉取整个项目。断线后使用 `Last-Event-ID` 续传；最终状态仍以数据库查询为准。当前 Web Mock adapter 还预留 `POST /api/v1/supervisor/runs` 流式入口，待 API/Agent 控制面完成后与其统一事件 DTO 和鉴权契约。

## 7. 后端模块

FastAPI 路由只做协议转换，业务放在 application service：

```text
modules/projects       项目创建、列表、成员权限
modules/imports        上传确认、文件校验、创建处理运行
modules/workspaces     工作区和图纸树查询
modules/runs           启动、取消、续跑、事件流
modules/wiring         表格分页、修订、版本与导出
modules/feedback       数据修订与规则建议
modules/profiles       图纸标准与版本查询
```

建议 API：

```text
POST   /api/v1/projects
POST   /api/v1/projects/{id}/source
GET    /api/v1/projects
GET    /api/v1/projects/{id}/tree
POST   /api/v1/projects/{id}/runs
GET    /api/v1/runs/{id}
GET    /api/v1/runs/{id}/events
POST   /api/v1/runs/{id}/resume
POST   /api/v1/runs/{id}/cancel
GET    /api/v1/projects/{id}/connections
PATCH  /api/v1/connections/{id}
POST   /api/v1/projects/{id}/exports
POST   /api/v1/feedback
```

上传采用“API 创建上传会话 -> 客户端直传 Storage -> API 确认”的方式，避免大 PDF 长时间占用 FastAPI 请求。

## 8. Agent 与多模板设计

### 8.1 公共流程

```mermaid
flowchart LR
    I["导入 PDF"] --> R["渲染页面"]
    R --> D["Profile 识别"]
    D --> C["Page Classifier Agent / Stage 1"]
    C --> S["Page Scanner Agent / Stage 2"]
    S --> X["确定性构建跨页任务"]
    X --> P["Cross-page Resolver Agent / Stage 3"]
    P --> V["确定性校验"]
    V --> M["结构化落库"]
    M --> E["结果版本/导出"]
```

PDF 渲染、页面索引、跨页任务生成、字段归一化和校验是确定性工作流步骤；三个子 Agent 分别负责页面身份分类、当前页连接扫描和单连接跨页补全。每个阶段只接收完成该任务所需的页面与上下文。ZH 首先通过兼容 Profile adapter 复用现有 `VLMClient`、Prompt、图片 Few-shot 和解析器；新 Agent 不复制或重写旧提取算法。

### 8.2 DrawingProfile 协议

阶段间“提交后从库读取”的改造另见 [ADR-0007](./adr/0007-durable-extraction-stage-boundaries.md) 和 [详细方案](./service/agent/stage-persistence-refactor-plan.md)。机制 Gate A 已实施：新协议保存不可变逐项结果/清单，下一阶段从数据库加载，接管过期 RUNNING、fencing 和最终收尾已验证。项目树原子发布，新协议元数据绑定 run 快照以保护历史证据。Gate B 内部上传/确认/原子入队及 HTTP 客户端/Fake 验收已完成，设计见 [ADR-0008](./adr/0008-gate-b-internal-business-imports.md)；真实模型人工验收、Web 和业务 JWT 代理仍待完成。

每个 Profile 提供：

```python
class DrawingProfile(Protocol):
    key: str
    version: str
    classification_prompt: Path
    page_scan_prompt: Path
    cross_page_prompt: Path
    few_shot_manifest: Path

    def detect(self, document: DocumentContext) -> ProfileMatch: ...
    def resolve_reference(self, ref: ReferenceEvidence, index: DrawingIndex) -> list[DrawingRef]: ...
    def normalize(self, connection: WireConnection) -> WireConnection: ...
    def validate(self, connection: WireConnection) -> list[ValidationIssue]: ...
```

公共 Graph 只调用接口。新增 ABB 时增加 `services/agent/profiles/abb` 和适配器，不修改振华 Prompt，也不在 Graph 节点中写 `if vendor == ...`。

当前文档提取已按 [ADR-0005](./adr/0005-retire-zh-workflow-runtime.md) 拆分：公共 `graphs/document_extraction` 调用注入的 `ExtractionPolicy`；ZH 的端子、方向、电流和引用策略位于 `agent_service.profiles.zh`。PDF/checkpoint/XLSX 位于 `infrastructure/document`，导出字段格式化通过 `ExportFields` 注入。`zh_workflow` 兼容目录已删除，所有 Python 调用直接使用新模块。

### 8.3 反馈闭环

用户已明确调整局部纠错语义，见 [ADR-0010](./adr/0010-in-place-confirmed-corrections.md)：确认后的直接修订和 Stage 2/3 重识别原位更新当前结果中的既有连接，不再克隆整个结果集合；连接 ID/线号保持稳定，使用集合 revision 和 record_version 校验，反馈 before/after 保留审计。旧文档的“局部修订创建新 accepted 版本”不再适用于新提交路径；完整提取仍保留结果代次。

```text
用户修订
-> feedback_items
-> 人工归因（数据问题 / Prompt / 引用解析 / 校验器）
-> 生成候选 Few-shot 或规则版本
-> 固定案例离线回归
-> 人工审核
-> 发布 profile_version
-> 新任务使用，新旧结果可复现
```

模型不得直接修改生产 Prompt。所有 Profile 文件、Few-shot 和校验器必须有版本和 checksum。

Supervisor 阶段 0 的会话边界、短期记忆和检测后人工确认约束见 [ADR-0006](./adr/0006-supervisor-short-term-memory-and-detection-acceptance.md)。该能力只服务类型检测验收，不替代项目级持久任务记忆；长期记忆需后续接入受权限保护的会话 repository。

### 8.4 Supervisor 主 Agent

AI 对话框由一个 Supervisor Agent 负责总揽。它只理解用户意图、请求缺失信息、选择 Profile Detection/Extraction/Correction/Improvement 工作流并转发阶段事件，不亲自执行端子识别，也不直接写生产数据库。

在线局部修订不再使用独立 Remediation Agent。Correction Workflow 根据连接证据和跨页索引确定性选择：直接 patch、Stage 2、Stage 2 + Stage 3 或仅确定性校验。用户接受修订后再异步进入 Improvement，分析模型感知、Prompt/Few-shot、跨页 resolver 或确定性规则问题。

## 9. 可靠性与可观测性

- 使用独立 Agent Worker 和持久队列执行长任务；Celery + Redis 是候选实现，最终选择在实现评审中确定，API 进程重启不得影响任务状态。
- 每个节点以 `run_id + stage + item_id` 作为幂等键。
- checkpoint 使用唯一临时文件、Windows 替换重试和锁，或直接使用数据库/Object Storage。
- 每阶段先写产物，再提交阶段完成事件，避免显示完成但产物不存在。
- 日志包含 `project_id/run_id/profile/stage/drawing_id`。
- VLM 调用保存模型、Prompt 版本、耗时、重试、token/费用（供应商支持时）和响应摘要。
- 不确定结果进入复核队列，流程继续，单页失败不能让整个项目丢失已完成结果。

## 10. 安全

- 规则资源库共享/直接可用契约以 [ADR-0012](./adr/0012-shared-ready-rule-library.md) 为准：所有登录用户可读；未停用包不再设置草稿/发布前提，新任务选最新包，既有运行 checksum 不变。该例外不扩大项目数据权限或取消规则编辑前的用户授权。
- 浏览器只持有 publishable/anon key，不得出现 service-role key。
- API 验证 Supabase JWT，并在所有查询中强制项目权限。
- Storage 默认私有，使用签名 URL；禁止公开整个 PDF Bucket。
- 上传校验文件类型、大小、PDF 页数和 checksum。
- Prompt、日志和错误响应不得泄漏 API key、JWT 或数据库密钥。
- 导出和用户修改写审计日志。

## 11. 迁移策略

1. 冻结旧 Vite 功能，只修阻断性问题。
2. 建立 monorepo 根配置和 `apps/web`，旧前端继续可运行。
3. 新建规范化表及 RLS，不删除 `wiring_tables`。
4. FastAPI 增加新项目 API，并用适配器调用现有 `wiring_graph.py`。
5. 新 Vite 工作台切换到新 API；右侧 AI 先做静态 UI。
6. 将运行目录迁出 `frontend/public`，接入 Worker 和事件流。
7. 抽取 `DrawingProfile`，先迁移 ZH，再接入 ABB。
8. 回填旧任务数据，核对数量和导出结果后下线旧接口与目录。

每一步都必须可以回退，禁止在新链路通过验收前删除旧代码。

## 12. 验收门槛

- 新用户登录、退出和路由保护正常；
- 上传 PDF 后数据库形成项目、工作区和图纸树；
- 处理事件可实时显示，刷新后可恢复；
- 表格支持服务端分页并可追溯来源图纸；
- XLSX 从指定结果版本生成且行数、顺序和字段一致；
- ZH 固定案例结果不低于当前基线；
- ABB 使用独立 Prompt/Few-shot，并通过独立回归集；
- 用户修订、规则建议和 Profile 发布均有审计记录；
- API、Agent、前端单测和关键端到端测试通过。
