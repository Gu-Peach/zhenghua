# Changelog

2026-10-17项目名改为双击原地编辑，目录/图纸按编号自然升序，图纸标签简化为006M01等编号；工作区暂不改名。32项浏览器与前端检查通过，仅前端改动。见[Web交付](../apps/web/changelog/2026-10-17-project-tree-inline.md)。

2026-10-17来源解释支持前端逐字显示和Markdown排版：大块/缓存/完成回复经过缓冲，支持立即显示、停止冻结和减少动态效果；26项浏览器与前端检查通过，无后端或数据变更。见[Web交付](../apps/web/changelog/2026-10-17-explain-typewriter.md)。

2026-10-17新增独立Profile Agent：统一提取Schema与可填写模板、规则/案例/原图诊断、确认建议或明确指令后编辑隔离草稿、用户确认Expected及规则包输出。SDK/CLI/可注册Router已离线验收，未接界面/正式发布，不改变现有Profile或项目。33+3项回归、strict mypy/Ruff通过，未调用真实模型或写业务库。见[Agent交付](../service/agent/changelog/2026-10-17-profile-agent.md)、[ADR 0026](../adr/0026-independent-profile-agent.md)。

2026-10-17接入Explain独立来源浮窗：行/页悬停入口、自动解释及流式追问、可展开淡色工具记录、关联原页/跨页图纸；8000 JWT/所有者代理→8100共享宿主，不新增端口。API 2.2.0及Pydantic/OpenAPI/TS契约同步，94项后端/Agent离线、22项浏览器、截图与前端检查通过。未真实模型/数据库调用或重启服务。详见[Web](../apps/web/changelog/2026-10-17-explain-panel.md)、[Server](../service/server/changelog/2026-10-17-explain-proxy.md)、[Agent](../service/agent/changelog/2026-10-17-explain-host.md)。

2026-10-16新增显式`zh_crop`列区域高清实验，原`zh`保持整页。2026-10-17用户确认本版可一并提交，已解除提取源码及配套测试/设计的本地忽略与专用提交拦截；运行结果、缓存和日志继续忽略。此次仅解除Git隔离，不改提取行为、生产发布状态或其他Agent改动，尚未执行提交。见[Agent记录](../service/agent/changelog/2026-10-16-zh-completion-crop.md)。

2026-10-16 Explain Agent扩展只读工具：支持页码/原理号/端子精确检索、关联原页/跨页图纸、分页覆盖和按需看图，LangGraph模型工具循环及HTTP/SSE/OpenAPI契约同步。51项Explain/共94项相关离线验证通过；未挂前端/服务、未运行真实模型或写库。额外旧Supervisor2项缺历史Prompt失败，详见[交付](../service/agent/changelog/2026-10-16-explain-retrieval.md)。

2026-10-16新增独立Explain Agent：LangGraph只读三表行事实、图纸索引与已保存证据，返回原页/跨页图片地址、差异/复核说明和多轮公开回答流。提供Python/CLI及宿主注入鉴权的router，业务接口/前端暂未接入；20项模块/59项组合离线测试及类型/lint通过，无真实模型或数据库调用、部署或旧Agent清理。见[记录](../service/agent/changelog/2026-10-16-explain-agent.md)。

2026-10-16修复独立Worker启动404：本地缺少20261016020000迁移，现已单独部署并登记历史，原函数/桶配置已备份；只读确认PostgREST四个RPC可见与API 2.1.0。未启动提取或模型调用，见[启动排障记录](../service/server/changelog/2026-10-16-incremental-extraction.md#后续启动排障)。

2026-10-16完成上传即提取的代码链路：独立Worker、三表增量发布、程序review后处理及JWT SSE工作台刷新；保留Stage2内部定向补全，无独立Stage3。API 2.1.0/OpenAPI/TS同步。62项Agent、19项API、15项浏览器、两种隔离库场景及Web检查通过；新增迁移尚未部署当前项目库，未调用付费模型或重启服务。见[Agent](../service/agent/changelog/2026-10-16-incremental-extraction.md)、[Server](../service/server/changelog/2026-10-16-incremental-extraction.md)、[Web](../apps/web/changelog/2026-10-16-incremental-extraction.md)。

2026-10-16三表结果新增start_terminal_coordinates/end_terminal_coordinates可空JSONB，API和前端类型同步，端点变更清理旧坐标；20项后端/Web检查/真实SQL与HTTP验证通过，本地迁移已部署，无Agent模型调用。图像高亮后续接入，见[Server记录](../service/server/changelog/2026-10-16-terminal-coordinates.md)。

2026-10-16登录后直接进入工作区，取消独立项目目录页；空库显示完整工作区和上传入口，项目管理移至侧栏。13项浏览器与Web检查通过，不改数据库/提取规则。见[Web记录](../apps/web/changelog/2026-10-16-workspace-entry.md)。

## 2026-10-16

- 明确先独立开发extraction/explain/profile能力、后接主调度的方向，整理旧Supervisor及冗余链路92文件审阅清单。自动审批拒绝批量删除/核心入口改写，尚未实施清理；仅新增设计和职责文档，不操作数据库或重启服务。见[ADR-0021](../adr/0021-independent-agents-before-orchestration.md)和[清单](../service/agent/independent-agents-retirement-inventory.md)。

- 按用户精简的ZH manifest保留003C01的1组初扫及5组补全/负例，清理未引用6图/12JSON，manifest v13和资源checksum同步；Profile仍2.1.1，不改变提取规则。仅静态核对，未运行测试/模型或写库。见[Agent记录](../service/agent/changelog/2026-10-16-zh-c01-example-cleanup.md)。

- 前后端接入三张新业务表：项目/规则引用/PDF保存、JSON图纸索引、批次结果与事务行级CRUD；API v2/OpenAPI/TS同步，上传不启动Agent，AI明确待接入。14项后端/10项浏览器、类型/lint/build和真实本地Auth/Storage/CRUD验收通过，合成数据清理，行管理RPC已部署。旧提取持久化另行接入，用户需重启8000加载新路由。见[ADR-0020](../adr/0020-three-table-management-contract.md)、[Server交付](../service/server/changelog/2026-10-16-simple-management.md)、[Web交付](../apps/web/changelog/2026-10-16-simple-management.md)。

## 2026-10-16

- 本地ZH2.1.1增强跨页读图：上下文v2不传来源端子/坐标/方向描述，允许任意边界回指，分别读取目标接口与针脚；唯一来源页PDF引用核对不可用地址并保留证据，补齐模块/母排案例。仅静态核对，不运行测试/模型或写库。见[Agent记录](../service/agent/changelog/2026-10-16-zh-cross-page-reading.md)。

## 2026-10-15

- 本地ZH2.1.0跨页补全改为目标图加state来源事实，初扫增加可选signal_name，保留业务页/Object Loc与原始引用；Profile控制输入模式，ABB/XMZ继续双图。仅静态核对，不运行测试/模型或写库。见[Agent记录](../service/agent/changelog/2026-10-15-zh-target-only-completion.md)。

- 公共提取图像预算改为实际图优先：压缩/整组减少Few-shot，输入自身超限才继续缩小；新增案例下限配置、删例metadata及缓存指纹，现有输入/总预算上限保留。仅静态检查，不运行模型或写库。见[Agent记录](../service/agent/changelog/2026-10-15-input-first-image-budget.md)。

- 所有模板主表对齐ZH14列（含色标空列/两端坐标），公共Graph、原生XLSX及本地脚本共用行映射和默认样式；ABB1.1.4/XMZ0.1.2补齐通用坐标说明/图像expected，未知留空。仅静态检查，不改数据库、不发布或覆盖旧结果。见[ADR-0019](../adr/0019-unified-extraction-table.md)与[Agent记录](../service/agent/changelog/2026-10-15-unified-table-coordinates.md)。

- 通用提取JSON Schema始终注入，ABB不再因关闭ZH专属约束而缺失字段契约；本地PDF入口新增文件型模型响应诊断，记录停止原因/用量，明确长度停止时避免重复格式重试。内部ModelResponse增加可选finish_reason，外部业务API不变；静态检查无新增lint，不跑测试/模型或写库。见[Agent记录](../service/agent/abb-output-contract-fix.md)。

- 公共提取模型请求统一控制实际图与案例图预算：实际图最长边2048px，请求总像素默认600万，保留原图/整图归一化坐标并记录发送尺寸，支持配置调节。静态检查无新增lint，未运行测试/真实模型或写库，服务商patch预算仍待实际复测。见[Agent记录](../service/agent/model-image-budget-plan.md)。

- ABB本地1.1.3按用户确认纠正为小圆圈放线、大圆圈端子，同段双标记只记一条；原理号标记数字或完整端子直接拼来源Sheet，更新图片expected及内部双图补全。静态检查通过，未运行测试/模型、不写库或发布。见[Agent修订记录](../service/agent/abb-circle-rule-update.md)。

- 本地PDF/拆页测试CLI支持--profile/--model及对应策略，强制内存/本地资源、不写库；帮助命令和三种模板只读绑定通过，未运行模型或提取。见[Agent记录](../service/agent/changelog/2026-10-15-local-profile-cli.md)。

- 补齐ZH003C01中间FC12组XA:11→003C31 XD10:1的双图样例，初扫五条引用保持；manifest v10/checksum同步，仅静态核对，未运行模型或写库。见[Agent记录](../service/agent/changelog/2026-10-15-zh-c01-middle-completion.md)。

- ZH本地2.0.5在端点冻结后沿对应相线读取Ie明确电流，保留原文且不计算系数/改取Set；003C01样例区分160A与80A，manifest v9/checksum同步。未运行测试/模型或写库。见[Agent记录](../service/agent/changelog/2026-10-15-zh-ie-current.md)。

- ZH本地2.0.4/manifest v8以003C01替换旧接收/跨页样例并清理独占旧图；端点/最终记录增加归一化端子坐标及本端图片PDF物理页，本地XLSX追加两列。静态资源/Schema/语法核对通过，未运行测试/模型、生成新XLSX或写库。见[Agent记录](../service/agent/changelog/2026-10-15-zh-c01-terminal-coordinates.md)。

## 2026-10-14

- ZH本地2.0.3按对应线路引用、附近元件与本端所在页Object Loc读取元件标识，X/XD排号不作为元件；内部补全仅可完善来源元件元数据，不改起点端子/原理号。expected/manifest v7/Schema与checksum同步，静态核对通过，未运行模型或写库。见[Agent记录](../service/agent/changelog/2026-10-14-zh-component-priority.md)。

- 经用户明确授权，本地zhenghua_test部署三张精简业务表并删除截图18张旧表/1个视图，旧业务数据不迁移。RLS/行版本/唯一键验证通过，Agent/Auth/Storage数据摘要不变，迁移登记完成；应用尚未适配，新上传暂不能走旧接口。见[Server实际部署](../service/server/changelog/2026-10-14-local-business-table-retirement.md)和[ADR-0018](../adr/0018-simple-extraction-business-tables.md)。

- 按用户要求交付三张精简提取业务表创建SQL草案（规则引用、项目、连接结果），新增实体表/所有者RLS/页级幂等键，保留旧schema；仅文件交付，未执行数据库或应用切换。见[ADR-0018](../adr/0018-simple-extraction-business-tables.md)和[Server记录](../service/server/changelog/2026-10-14-simple-extraction-schema-sql.md)。

- XMZ大车卷盘本地规则使用prompts/xmz资源，0.1.1对齐放线标记/最近端子及程序端子排，样例expected仅取图片事实、不补人工表外部字段；保持独立页标策略，静态检查，不跑测试/模型或写库/发布。见[Agent记录](../service/agent/changelog/2026-10-14-xmz-image-only.md)及[ADR-0015](../adr/0015-zh-gantry-reel-profile.md)。

- 本地ZH测试脚本隔离其他模板缺失资源导致的ProfileRegistryError，ZH自身仍校验，终端/失败产物显示具体原因。只读资源绑定确认当前ZH可用，未运行提取/模型或写库。见[Agent记录](../service/agent/changelog/2026-10-14-local-profile-isolation.md)。

- 明确ZH初扫以放线斜杠为搜索起点，找到最近端子/跨页箭头后按同段箭头定向；原理号和端子文字仅用于读取/匹配。仅本地规则/调用指令修改，未运行测试/模型或写库，准确率待用户复测。见[Agent记录](../service/agent/changelog/2026-10-14-zh-marker-first.md)。

- 按用户新目录集中提取实现到src/agent/extraction_agent，共享包名src及入口/资源引用同步；61份源码只移动/改引用，254份Python静态AST对照保持非引用实现不变。未运行业务测试、模型或写库。见[ADR-0017](../adr/0017-extraction-agent-directory.md)及[Agent记录](../service/agent/changelog/2026-10-14-extraction-agent-directory.md)。

- 同步ZH实际提取样例与Prompt：C01完整端子/排号、C02元件描述、FO2设备/实际排号分离，manifest v6/资源摘要更新；不运行测试/模型或写库。见[Agent记录](../service/agent/changelog/2026-10-14-zh-expected-alignment.md)。

- 按用户要求删除ZH离线regression_cases及对应expected/独占图片，同步manifest v5、资源条目和测试引用，保留运行时初扫/内部补全案例。本轮未运行测试/模型或写库。见[Agent清理记录](../service/agent/changelog/2026-10-14-zh-example-cleanup.md)。

- 用户明确修订ZH放线口径：读取标记两侧直接端子、遇端子停止，业务端子排仅后处理映射。ZH本地2.0.2精简Prompt并保留电流约束，新增M23八条用户确认样例；本轮不运行测试/模型、不写库、不发布。见[ADR-0016](../adr/0016-zh-direct-terminal-segments.md)及[Agent记录](../service/agent/changelog/2026-10-14-zh-direct-terminals.md)。

This directory records cross-module architecture and product behavior changes.
Detailed application work is archived under `docs/apps/`; service work is
archived under `docs/service/`.

详细变更见 [CHANGELOG.md](./CHANGELOG.md)。

## 2026-10-13

- Supervisor改为专业电气图纸与线表助手：日常CHAT流式回答且不分派任务/展示确认卡片，任务先说明后卡片，真实上传PDF保留类型确认及Stage 1/2提取。SSE公开回答流和前端稳定消息同步，领域契约6，业务Server接口不变；77项离线和21项浏览器夹具/Web检查通过，无真实模型/业务库写入或已有Agent重启。见[Agent](../service/agent/changelog/2026-10-13-supervisor-chat.md)与[Web](../apps/web/changelog/2026-10-13-supervisor-chat.md)记录。

- 补齐 [Web](../../apps/web/README.md#启动)、[Server](../../services/server/README.md#启动)、[API](../../apps/api/README.md#本地启动) 和 [Agent](../../services/agent/README.md#启动) 的本地启动说明，统一仓库根目录执行方式、端口及启动顺序，明确 Agent 开发 Worker 与 Server 事务连接。仅文档更新，启动命令语法/入口静态核对通过，未安装依赖、启动服务或操作数据库。

- 根据002.C/002.M原图核对修正本地ZH2.0.1：方向缺失不再默认确认起点，原始引用优先解析，同源分支在补全前保留，端子身份/证据不足降级复核。40项冒烟与7项接口/兼容边界回归；不写数据库、不发布、不重跑真实模型，旧结果保留。见[Agent记录](../service/agent/changelog/2026-10-13-zh-stage2-quality.md)。

- 本地新增 ZH 大车卷盘 SH.NO. 网格模板 experimental Profile，独立页标/引用适配、三类模型 Prompt 各两组真实图像样例；明确 XLSX 业务分类/别名与原理图事实的区别，既有 ZH/ABB 不变。未上传/写数据库/发布，真实字段质量待确认。见 [ADR-0015](../adr/0015-zh-gantry-reel-profile.md) 与 [核对记录](../service/agent/zh-gantry-reel-review.md)。

- 新增本地 Stage 2 分组测试与标准 12 列 XLSX 导出，色标留空；真实 002.C/002.M 共 12 页、121 条，31 条待复核，14 项离线冒烟通过。仅本地内存与文件，无数据库/Storage/规则发布；页码 0 占位兼容保持严格合法编号校验。见 [Agent 执行记录](../service/agent/changelog/2026-10-13-local-stage2-groups.md)。

- 分支提取改为 Stage 1 分类 + Stage 2 逐页闭环，删除独立 Stage 3，内部双图补全后保存再推进；ZH 放线/箭头替代端子白名单，保留实际端子与可追溯分类。10 项离线冒烟通过，本轮不连接/写入数据库、部署 migration 或发布规则；业务版本仍最终原子提交。见 [ADR-0014](../adr/0014-stage2-page-extraction-workflow.md) 与 [Agent 记录](../service/agent/changelog/2026-10-13-stage2-page-workflow.md)。

- 按用户决策，规则归因建议经一次确认后直接构建并启用新包，取消模型评测/二次审核门禁；保留旧版本、权限/冲突保护及原子审计，已有项目不重绑。Agent/HTTP/聊天/终端同步，详见 [ADR-0013](../adr/0013-confirmed-rule-update-without-evaluation.md) 和 [实施记录](../service/agent/changelog/2026-10-13-confirmed-rules.md)。

- 项目切换改为保留框架、局部加载，目录不随选择重拉；Server 项目列表按创建时间/ID 固定排序，更新/选择不置顶。17 项浏览器回归、29 项 Server 默认测试及 Web 检查通过，见 [Web 记录](../apps/web/changelog/2026-10-13-stable-project-switch.md) 和 [Server 记录](../service/server/changelog/2026-10-13-stable-project-order.md)。

- 左侧项目目录点击名称/文件夹直接切换项目，箭头控制当前项目折叠，移除二次“打开项目”入口。17 项浏览器夹具及 Web 检查通过，见 [记录](../apps/web/changelog/2026-10-13-project-folder-navigation.md)。

- 导航和搜索按容器水平居中，线表记录改为原位编辑，复用既有 PATCH/版本锁/幂等和审计，取消编辑弹窗；16 项浏览器夹具、Web typecheck/lint/build 与桌面/窄屏截图检查通过。见 [Web 记录](../apps/web/changelog/2026-10-13-centered-inline-edit.md)。

- 工作台精简：新增端子改为最右侧加号，移除全部工作区按钮和重复项目概览；导航显示当前项目名，左侧项目可折叠并移除 PDF 中间节点；聊天去掉独立当前阶段卡片。13 项浏览器回归、Web typecheck/lint/build 和截图检查通过，见 [Web 记录](../apps/web/changelog/2026-10-13-workbench-cleanup.md)。

- 图纸库改为项目→工作区→图片原地展开和预览，替代平铺点击切换线表。聊天从固定右栏改为右下角按钮控制的悬浮窗口，保留草稿、任务订阅及人工确认；13 项浏览器夹具、前端 typecheck/lint/build 和桌面/窄屏截图检查通过。见 [Web 记录](../apps/web/changelog/2026-10-13-directory-floating-chat.md)。

## 2026-10-12

- 规则库取消手工包草稿门槛：所有登录用户共享读取，写入后直接可用；同 key 新任务选择最新 active 版本，历史 checksum 保留，Improvement 隔离候选及其精确回滚仍受审核范围保护。三个 additive migration 已应用并通过非创建者 RLS、空库/旧数据重放。ABB 1.1.2 已接入独立三阶段 adapter/policy、上传并读回校验，当前可执行但真实模型字段准确率仍待验收。见 [ADR-0012](../adr/0012-shared-ready-rule-library.md)、[Server 记录](../service/server/changelog/2026-10-12-shared-rule-library.md) 和 [Agent 记录](../service/agent/changelog/2026-10-12-abb-ready-profile.md)。

- 候选目标评测的 Stage 2 上下文补齐明确起点定位，保留正确终点隔离和严格起点匹配；不改 Profile/数据库/发布门禁。32 项相关离线回归通过，真实模型未运行，旧冻结评测不会因重载或 resume 自动重测，见 [Agent 修复记录](../service/agent/changelog/2026-10-12-evaluation-source-locator.md)。

- 图纸库只展示当前项目的图纸目录，不展示旧的项目文件夹列表或工作区分组；线表左侧导航仍保留工作区层级。该条最初实现了规则状态显示，后续已由同日共享规则库决策取代。
  - 收尾增加空目录/跨工作区定位回归，最终 11 项浏览器夹具与 Web typecheck/lint/build 通过，截图已检查。ABB 创建者已只读核对，用户当前账号可见性尚待确认，见 [Web 记录](../apps/web/changelog/2026-10-12-resource-library.md)。

- 按用户要求将 ABB 样例精简为三个阶段各一例、图片 1/1/2 张；abb@1.1.1 草稿上传私有 Bucket，18 文件读回核验通过，不覆盖旧不可变包或生产绑定。见 [Agent 精简记录](../service/agent/changelog/2026-10-12-abb-resource-compact.md)。

- ABB 1.1.0 三阶段资源改为独立 Prompt/图片/manifest/expected/task 格式，上传私有 agent-profile-assets 草稿并读回验证 45 文件；不替换生产包或项目绑定。独立确定性策略和真实模型验收尚未完成，见 [Agent 资源实施记录](../service/agent/changelog/2026-10-12-abb-resource-draft.md)。

- 规则库支持基于已发布模板新建规则包并自动注册给 Agent；创建者可确认删除/停用，新任务不再选择，历史项目仍按冻结 checksum 读取资源。复用现有私有 Bucket、包元数据和发布 RPC，无 migration；新增 JWT 业务接口、Web 表单/确认和跨进程 Registry 刷新。离线验证与环境限制见 [Server 实施记录](../service/server/changelog/2026-10-12-rule-package-lifecycle.md)。

- 独立结果审校对账遇到 `matched` 但缺少 `connection_id` 时改为保存为 `needs_review` 并继续后续页面，避免单个模型结构错误中断整批；该行不计为已确认匹配。离线回归覆盖，未调用真实模型。

- 规则候选新增服务端 PROFILE_EVALUATION：固定三阶段/负例及 accepted-feedback 目标同图比较，持久评测 receipt，人工审核和发布分别确认；不可变 Bucket 包通过既有 RPC 发布，旧项目 Profile 冻结保留。公开审核契约要求 evaluation_run_id，旧外部报告不作为发布证据。49 项离线回归通过，未调用真实模型或发布候选，见 [Agent 记录](../service/agent/changelog/2026-10-12-candidate-release.md)。

- 用户授权后的真实模型 Web→Server→现有 Agent 联调：PDF 上传/检测/人工确认后三阶段成功落库（5 页/13 连接，约 226 秒），真实 Bucket 三阶段资源面板和图纸索引通过。浏览器退出，纠错/确认/归因仍待验收；新增同项目续跑避免重复提取。自动审批服务自身模型权限 403 使续跑命令未执行，临时数据保留，不改 Schema/Agent 核心/test0。见 [联调状态](../service/server/changelog/2026-10-12-live-agent-acceptance.md)。

- 按用户授权补齐端子新增/删除：Server 既有表原子事务、稳定 ID/线号/代次、完整证据审计与版本/幂等保护，Web 入口与 OpenAPI 同步。24 项默认 API/5 项浏览器夹具通过；真实一次性 Auth/数据库/Storage/API/浏览器增改删、双图及越权/过期/冲突/重放/审计失败回滚通过并清理，不改 test0/Schema/Agent 核心。完整上传/纠错验收未完成：共享队列 Fake 提取测试在 Worker claim 失败，有用户活跃消费者，未停服务。详见 [Server 最新记录](../service/server/changelog/2026-10-12-real-workbench.md) 与 [ADR-0011](../adr/0011-manual-connection-insert-delete.md)。

- 修复 Gateway 误截补丁 JSON 字符串内嵌 Markdown 示例：先解析完整 JSON、仅剥离真正外层 fence。实际失败输出只读重放及31项相关离线测试通过；严格校验/发布门禁不变，未调用模型或写数据库。见 [Agent 记录](../service/agent/changelog/2026-10-12-embedded-fence-json-fix.md)。

- 修复 ProfilePatchBuilder 的模型输出契约：只读 Trace 确认 invalid_json，动态注入实际 JSON Schema、完整文件字符串/转义/包相对路径要求；严格校验及发布门禁不变。11 项相关离线回归通过；未重复修订数据或调用真实模型，详见 [Agent 修复记录](../service/agent/changelog/2026-10-12-profile-patch-output-contract.md)。

- 独立结果审校支持跨页引用页码 null/空白：保留原始引用并标记待复核，继续后续页面；修复已访问页循环漏检。11 项离线回归通过，未调用真实模型，未改生产 Agent/数据库。脚本修改生成新验证快照，旧报告保留但缓存不复用，见 [审校说明](../test/agent-run-001/VALIDATION_README.md)。

- 完成性核对补齐规则包逐阶段 manifest 样例展示、纠错确认/刷新/归因说明与候选状态、内部 Agent 鉴权错误与上传请求头边界。21 项 Server、5 项浏览器夹具及真实资源包只读验证通过；完整真实验收与端子增删范围仍需用户选择，目标未完成。见 [完成性记录](../service/server/workbench-completion-audit.md)。

- 真实工作台收尾修复：首次自动检测在 StrictMode 下被取消、最终确认消息遗漏、阶段卡片重复、错误待确认状态；补共享单元字段编辑、续传/重连、图片签名刷新、Auth 并发续期/过期退出与完整上传响应匹配。18 项 Server、4 项浏览器夹具回归通过；真实登录/写入/模型联调及端子增删范围仍待确认，不改数据库或 Agent 核心。

- 开始真实 Web/Server 接入：新增 apps/api 与 services/server，Supabase Auth/项目权限、真实树/线表分页与手动修订、私有图纸/规则资源、Agent HTTP/SSE 安全代理；Web 切换真实接口、组首页码/线号、表格下方跨页预览、规则样例面板与可缩放布局。无 migration/Agent 核心改动。Fake API/Web 与只读真实库验证已执行，写入和真实模型全链路验收仍未完成，见 [实施进度](../service/server/changelog/2026-10-12-real-workbench.md)。

## 2026-10-11

- Fixed Improvement diagnosis requests to include the runtime Diagnosis JSON Schema and exact field/enum constraints, retaining strict validation and compatible provider settings. Twenty-four focused offline checks passed; existing committed corrections were preserved. Reload and resume only the failed diagnosis run for live verification. See [Agent record](../service/agent/changelog/2026-10-11-improvement-diagnosis-schema-fix.md).
- Fixed scoped-correction source matching so location and device identifiers are not compared as equivalent fields; missing, ambiguous or duplicate targets now fail explicitly instead of silently omitting fixes. Added safe Worker failure-location logs. Thirty-three focused offline checks and cached Stage-2 read-only replay passed; no database writes, real-model call or service restart. See [Agent record](../service/agent/changelog/2026-10-11-scoped-correction-source-matching-fix.md).
- Prepared three user-authorized test0 terminal-error injections for direct-answer, same-page and cross-page acceptance, checking source/target PDF evidence first. Backups, expected fields and natural-language input are stored in ignored local run assets; only the three latest connections were changed and revision counters advanced. No Profile mutation, model execution or service restart.
- Added the first HTTP-only mixed-correction terminal acceptance client with human confirmation, SSE/stage outputs, stable-row checks, and honest no-rule-issue/inconclusive/unexpected-candidate-rejection outcomes. Added owner-scoped structured model-output views without hidden reasoning or prompts. Offline mock checks passed; no real model, database mutation or service restart. The second rule-issue script is intentionally deferred. See [record](../service/agent/changelog/2026-10-11-correction-terminal-acceptance.md).
- Changed confirmed scoped corrections to in-place updates per user request (ADR-0010): stable connection/unit/evidence IDs and wire numbers, result revision and record-version checks, feedback audit, and idempotent receipts. Full extraction still creates generations. Applied additive local migration `20261011020000`; focused offline and synthetic rollback checks passed. Existing test0 values/history were preserved; services were not restarted. See [record](../service/agent/changelog/2026-10-11-in-place-corrections.md).
- Fixed post-confirmation Improvement startup: use the correction run's real PDF reference instead of its feedback ID, preserve the accepted Profile, and return committed-result details even when asynchronous diagnosis startup fails. Read-only inspection confirmed case-A result version 2 was already accepted; no correction was rolled back/recommitted. Five focused tests and strict typing passed. See [Agent record](../service/agent/changelog/2026-10-11-confirmation-improvement-source-fix.md).
- Fixed case-A Supervisor schema validation: accept integer page/wire search terms as text, support directional terminal selectors in both result repositories, and inject the actual output JSON Schema. Failed structured responses retain private traces while HTTP exposes only schema/field error types. Twenty-three focused offline tests and strict typing passed; an isolated real-model decision matched one connection without dispatching or writing results. See [Agent record](../service/agent/changelog/2026-10-11-supervisor-correction-schema-fix.md).
- Applied and registered the additive Profile-package migration on local `zhenghua_test`, published the unchanged ZH bootstrap matching test0's frozen checksum, verified all 29 resource files/private Storage/anonymous isolation, and preserved wiring-data digests. Fixed empty-success responses from void PostgREST RPCs (six focused tests passed). No Agent restart, runtime-mode switch, or real-model call. See [deployment record](../service/agent/changelog/2026-10-11-profile-package-deployment.md).
- Implemented correction mixed-batch orchestration, one-proposal version commits, durable scoped stage artifacts, enriched diagnosis evidence, self-contained immutable Profile package adapters and gated publish/rollback hooks. Twenty-six focused offline tests and strict typing/lint passed. Local Supabase is not running, so migration/package deployment and live acceptance remain pending; non-extraction RUNNING takeover and conversation durability are not implemented. See [implementation/deployment record](../service/agent/changelog/2026-10-11-correction-packages-implementation.md).
- Implemented Gate B internal business PDF import, human-confirmed frozen Profile/run creation, atomic run/event/queue registration, published project-tree and versioned result read models, resumable SSE, and a tools-free terminal HTTP client. Fake HTTP and local Supabase/Fake model verification passed; real-model field accuracy and browser JWT/Web integration remain pending. See [Agent record](../service/agent/changelog/2026-10-11-gate-b-implementation.md).
- Documented the proposed Correction Agent resource-package and mixed-batch design. Cross-page re-extraction remains Stage 2 -> Stage 3; correction acceptance reuses test0 with manually injected errors through the existing Supervisor HTTP interface, with no new terminal script. No code, migration, Bucket package, or production Profile was changed. See [plan](../service/agent/correction-agent-refactor-plan.md) and [ADR-0009](../adr/0009-profile-resource-package-storage-and-correction-batches.md).

## 2026-10-10

- Completed Gate A mechanism acceptance: protocol-2 durable stage snapshots/read barriers, RUNNING takeover/fencing, immutable classification publication and finalization receipts. Ten real-Supabase/Fake-VLM scenarios passed in batches, including isolated worker-process recovery; 21 ordered migrations passed empty/legacy synthetic verification. Legacy runs remain compatible; Gate B user-flow integration and real-VLM evaluation remain pending. See [implementation record](../service/agent/changelog/2026-10-10-gate-a-implementation.md).
- Restored the local Git metadata from the retained `.git-new` repository, preserving the existing history and `Gu-Peach/zhenghua` origin. Excluded local extraction outputs, caches and environment secrets; enabled tracking of versioned Agent prompt images. This repository maintenance does not implement the proposed stage-persistence changes.

- Documented the proposed durable extraction-stage boundary: typed per-item database outputs, immutable manifests, atomic commit/event barriers and database-backed inputs for the next stage. See [plan](../service/agent/stage-persistence-refactor-plan.md); no runtime or database change has been applied for this proposal.
- Refined that proposal to V1.1 after consistency review: leased RUNNING takeover with fenced mutations, authoritative item sets, recoverable finalization receipts, atomic classification-tree publication, explicit digest/conflict rules and separate mechanism/user-flow acceptance gates. Documentation only; runtime and migrations remain pending.
- Fixed the OpenAI-compatible model request boundary so structured Supervisor context is serialized as JSON string content; multimodal message arrays remain unchanged. This resolves the stage-zero 400 error from providers that reject object-valued `message.content`; the Agent service must reload this code before retrying the live test.
- Made provider-side `response_format` opt-in. Local structured output validation remains enabled through Pydantic, while endpoints that require a server startup flag are no longer sent `response_format` unless `ModelRequest.json_mode=true`.
- Added a detection-only Supervisor conversation flow with terminal-driven HTTP acceptance, streamed planning/dispatch messages and explicit Profile confirmation. The API now remembers recent turns, attachments and pending decisions in bounded per-user, per-conversation process memory; task checkpoints remain separate, and restart/shared-instance or long-term conversation persistence is not implemented.
- Removed the remaining `agent_service.zh_workflow` import-compatibility package and switched its tests to current modules. Legacy Python import paths are no longer supported; existing Agent HTTP/Worker and CLI entry points retain their current behavior.
- Removed the retired adjacent-page segmentation and batch-extraction implementation, its dedicated checkpoint/planner/configuration and compatibility exports. Production Agent/CLI continue to call the new document Graph directly; retained legacy imports forward current capabilities to that same implementation.
- Retired the production dependency on `zh_workflow`: shared document Graph, domain stage models, PDF/checkpoint/export infrastructure and injected ZH Profile policies now own the implementation. Legacy imports forward to those modules; stage artifacts, result proposals and database contracts retain their shapes. See [Agent migration record](../service/agent/changelog/2026-10-10-document-workflow-migration.md).

## 2026-10-08

- Established the project, workspace, drawing and wiring-result domain model.
- Added the gradual monorepo migration plan while preserving legacy frontend
  and backend implementations.
- Selected React + Vite + TypeScript for the new `apps/web` application.
- Standardized the frontend source structure around API, component, hook,
  layout, router, store and view ownership.
- Added module-specific documentation archive rules to `AGENTS.md`.
- Established the Supervisor-led orchestration boundary and deterministic correction routing; runtime Graph integration remains pending the M4 gate.
- Added isolated Page Classifier, Page Scanner and Cross-page Resolver subgraphs backed by the existing ZH stage adapter.

## 2026-10-09

- Completed the Agent-to-Supabase data path: full extraction now creates normalized draft/review result versions atomically; confirmed corrections create accepted versions with optimistic checks and accepted-feedback audit. Correction bundles, model traces, Profile candidates, release gates, evaluations and lifecycle audit are durable in Supabase. Stage agents still cannot issue arbitrary writes, and Profile activation remains human-gated.
- Applied the normalized domain and Agent runtime migrations to the local Supabase stack, added the private `project-assets` hierarchy, persistent run/event/artifact/proposal/checkpoint repositories, a lease-based queue, source-PDF checksum verification, classified page publication, and signed-URL access. The legacy table and public bucket remain untouched; hosted Supabase deployment and Server-owned result transactions remain pending.
- Updated the `apps/web` Mock Supervisor workflow to start only after explicit user activation; PDF workspaces and split drawings appear after Stage 1 completes, while thought and Agent status events stream in stage order.
- Added the Agent Run/Worker/SSE control plane, Supervisor and scoped Correction workflows, plus a sandboxed evaluation and human-gated Profile candidate lifecycle. Production persistence and Server/Web integration remain explicit follow-up work.
- Added a normalized wiring schema migration: project/workspace/drawing/result-version ownership, terminal-strip units with database-assigned wire numbers, queryable connection columns, evidence, RLS and a flattened search view. The legacy JSONB table remains unchanged and remote application is still pending.
- Completed the offline Supervisor orchestration V2: internal first-page Profile Detection, controlled multi-key result lookup and versioned correction, three-state cross-page routing, accepted-feedback diagnosis, explicit Profile candidate authorization, and sanitized diagnosis/candidate events. Production Supabase/Server adapters remain pending.
