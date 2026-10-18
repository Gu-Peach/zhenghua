# TODO

> 这是当前执行清单，不替代 [开发路线](./roadmap.md)。每次开发只把本次可交付内容放入“进行中”。

## 进行中

- [ ] PDF遍历完成统一显示处理完成：Worker正常返回后提交finished，单页错误保留诊断；前端兼容旧EXTRACTION_PARTIAL终态，真正中断仍失败。仅静态/隔离浏览器检查，不重跑模型或改历史业务数据。

- [x] 线表提取失败提示增加右侧关闭按钮：仅隐藏当前提示，保留重试行为，新失败重新展示；类型/lint/build及隔离浏览器桌面/窄屏/长文本/键盘/重试核对通过，8份截图在.runtime。未操作真实提取任务/数据库/服务，见 `docs/apps/web/changelog/2026-10-18-extraction-notice-dismiss.md`。

- [x] 纠正整组端点调换归属：所属页/工作区及关联索引固定，仅端点/坐标对象交换；旧迁页方案前后端禁用。新迁移20261018040000本地部署，按快照事务恢复实际4行到006C01/006.C，已确认端点/坐标与其他行不变。70项Agent、5项Server API、10项隔离SQL、25项编辑/预览浏览器及类型/lint/build/Ruff/mypy通过；未调用真实模型或重启服务。见 `docs/service/server/explain-swap-origin-correction.md`。

- [x] ABB小圆点规则本地1.2.1：补母线输入/同段双标记、完整Q3:1/X1:11端子、编号拼Sheet及无编号回退；同一来源图27条示范，内部补全同步，ZH十四列/坐标和XMZ不改。2Python AST/Ruff、27条Pydantic、7项manifest摘要/路径及绑定通过，未运行测试/模型或写库/发布。见 `docs/service/agent/changelog/2026-10-18-abb-marker-endpoints.md`。

- [x] Explain删行排障完成：后续物理删除清理业务副本/相关方案，明确工作区主动查询。原空表处理曾采用“跟随新页”，该约定已由上方归属修正撤回，4行已恢复006C01。删除函数迁移20261018030000保留，历史验收见 `docs/service/server/changelog/2026-10-18-explain-delete-relocation.md`。

- [x] 单页初扫失败隔离：独立失败分支和尝试记录，后续页继续，失败页不进入完成缓存；遍历后EXTRACTION_PARTIAL汇总并保留重试。4文件Ruff/AST及Graph构建通过，定向mypy仍有5条原有问题；补回归未运行测试/模型，未操作任务/数据库/服务。由用户重启Worker后原项目重试，见 `docs/service/agent/changelog/2026-10-18-extraction-page-failure.md`。



- [x] 修复Profile辅助编辑诊断/提案FILE_NOT_READABLE：区分规则原文、已查看图纸和用户结果，工具/建议持久化共用校验，失败提示可恢复；新增10项复现/恢复用例，86项Agent和5项Server离线回归、6源码mypy、Ruff及前端类型/lint/build通过。契约说明同步，不改实际草稿/已发布规则或操作用户服务；重载8100后原草稿新轮复试，真实模型未运行。见 `docs/service/agent/changelog/2026-10-18-profile-evidence-validation.md`。

- [x] 平台提取入口对齐本地Stage2脚本：共享请求/禁色标、页面元数据、模型Gateway与14列字段投影，新增请求指纹/过滤前计数并允许ZH第0列。4初扫与14补全离线消息一致，154条表值不变/发布投影一致，15文件Ruff/AST、105摘要及两CLI帮助通过；13源码类型检查与HEAD基线相同18条问题，无新增。未运行pytest/Fake VLM/真实模型、不写库或启停服务；用户重启Worker后新上传2.2.1验证。见 `docs/service/agent/changelog/2026-10-18-extraction-entry-alignment.md`。

- [x] 扩展Profile现有规则编辑：Storage/本地规则派生草稿、双击手动编辑、带图纸/实际结果的工具聊天、diff/同意后发布替换新版及引用感知回收；API2.6.0与契约同步。76项Agent、26项Server、2项独立SQL与59项浏览器及最终25项复验、类型/lint/build/Ruff/11源码mypy通过；真实ZIP临时导入通过，新迁移本地部署且业务摘要不变。未代发规则、改实际草稿、运行真实模型或启停用户服务；需用户重载8000/8100。见ADR-0032与模块交付。

- [x] 对齐ABB1.2.0/XMZ0.2.0与ZH局部补全结构：各1组来源初扫/对应目标案例，目标图+冻结事实、独立图框裁剪与坐标回映；分页资源/ZH规则保留。7源码strict mypy、11文件Ruff、13份AST、四Profile绑定/Schema/77摘要及两CLI帮助通过；60原资源及5份HEAD记录图像摘要不变。已补回归但未运行测试/模型，不写库/发布，用户新目录复测。见 `docs/service/agent/changelog/2026-10-17-abb-xmz-alignment.md`。

- [x] 完成zh_crop 2.2.1空响应/重复N线修正：默认值前校验、已有最多两次重试、失败/视觉原因保留且继续后续连接；新增005C01两组N线对照、独立1/7案例目录，仍只选一例。3文件Ruff/AST、适配器strict mypy、四Profile绑定、Schema/路径/68摘要及原案例逐字节核对通过；Graph相关13条类型错误与HEAD相同，无新增。已补回归但未运行测试/模型，不写库/覆盖旧结果，用户用新目录复测。见 `docs/service/agent/changelog/2026-10-17-zh-completion-response.md`。

- [x] Profile发布“数据操作失败”修复：只读确认包已上传但缺发布RPC/迁移；既有20261017010000迁移已原子应用到明确的本地库并登记，业务/Storage摘要不变，可信角色权限与REST Schema可见性通过。ZIP摘要匹配，用户规则尚未登记；未代为发布或启停服务。26项后端与2项独立SQL、Ruff/2源码mypy通过，补缺接口的安全错误码与重试复用验证。用户直接重试发布即可，见Server发布迁移排障记录。

- [x] Profile发布负例改为可选：取消缺负例拦截，保留已有负例的校验/打包/使用，更新对话及向导提示。34项Agent离线、17项浏览器及类型/lint/build、Ruff/2源码mypy通过，相关桌面/窄屏截图核对完成。未代为发布或操作实际数据库/服务，重载8100并恢复对话即可重新计算发布资格。见负例可选记录。

- [x] Profile更换原图后NO_CROSS_PAGE_TASK修复：只读定位到revise_scan强制覆盖新原图；区分同图纠正/换图重扫、隔离旧图事实与后续反馈，补全前核对结构化任务。22项对话与7项Wizard离线回归、1项浏览器阶段切换冒烟及Ruff/2源码mypy通过；不改真实草稿、业务库或用户运行服务，需重载8100后在原对话重建并确认新初扫。见换图交付与ADR-0031补充。

- [x] Profile重复确认修复：只读确认对话已保存但ready=false与目标图约束形成循环；新增补全→初扫修正候选路径，复用原图、优先用户纠正、依赖失效并明确确认。24项相关Fake/Mock、11项规则聊天浏览器及类型/Ruff/lint/build通过，未改实际草稿/业务库、调用真实模型或启停用户服务；需重载8100后在原草稿继续。见ADR-0031。

- [x] Profile第二阶段失败排障代码完成：只读确认分类/样图已保存，补齐终端日志/私有响应、分类错误码/诊断编号、生成完整外层Schema和配置传递；9项诊断及既有回归、10项聊天浏览器和类型/Ruff/lint/build通过。未重跑付费模型/改实际草稿/业务库或用户服务；历史失败无响应，实际根因与成功复试仍需用户重载8100后确认。见Profile模型错误记录。

- [x] 第一阶段PDF随机两页工具与自动聊天接入：只渲染选中页、保留物理来源与幂等回执，两份分类Expected；原PDF/其余页不落盘，解析/渲染失败不添加附件，后两阶段禁止复用PDF样图。25项相关回归、33项原Profile、60项浏览器、类型/Ruff/lint/build及实际PDF样图/桌面窄屏截图通过；未运行真实模型或操作用户服务/业务库。见ADR-0030。

- [x] Profile引导式多轮聊天完成：图片/文字追问、三阶段公开读图依据及候选纠正、明确确认后保存规则/Expected、来源冻结、持久对话恢复与手动发布，Agent/Server/OpenAPI/TS同步。57项浏览器及最后12项入口回归、相关Agent/Server Fake回归、类型/lint/build通过；无新增迁移，未启停用户服务/调用真实模型或写业务数据库。见ADR-0029及Profile对话交付。

- [x] 排查新建规则草稿404：8000运行2.2.0缺草稿路由，8100已有接口，源码2.3.0路由正确；3项Mock链路测试通过并补启动排障说明。未启停用户服务或写业务数据库；用户重载8000后再进行实际界面重试。


- [x] 线表/图纸预览增加可拖拽分隔条、键盘调宽和双击复位，修复缩放百分比/长标题溢出；45项离线浏览器、类型/lint/build及桌面/窄屏截图通过。仅前端修改，未操作真实模型/数据库或用户服务。见 `docs/apps/web/changelog/2026-10-17-preview-resize.md`。

- [x] 按用户指定将三个Agent展示版本统一为1.0.0，同步页面说明；4项智能体中心离线浏览器冒烟、类型检查、lint和生产构建通过。Skill版本继续读取实际规则包，未改后端/数据库或启停用户服务。

- [x] 前端智能体中心/三Agent卡片/zh_extraction等提取Skills，规则库迁出项目；全量线表与五列图纸预览双模式，右侧上下原/目标图及端点坐标标注，缩放/缺坐标/失败/旧响应处理。44项离线浏览器、typecheck/lint/build及桌面/窄屏截图通过。未知Agent版本/连通性如实显示，后端/数据库/提取规则和用户服务未改。见 `docs/apps/web/changelog/2026-10-17-agent-center-preview.md`。

- [x] 前端项目树/当前项目标题双击原地编辑：Enter/失焦保存、Esc取消，失败保留草稿，移除改名铅笔/window.prompt；按用户确认工作区暂不改名。目录/图纸编号自然升序，主标签仅显示006M01等编号；32项浏览器回归、typecheck/lint/build及桌面/窄屏截图通过。后端/业务键/处理顺序未改，未操作真实数据库或用户服务。见 `docs/apps/web/changelog/2026-10-17-project-tree-inline.md`。

- [x] 2026-10-17撤销提取Agent本地忽略与专用提交拦截：核对原hook摘要并备份后，仅移除实验隔离块及专用hook；10个新增源码/Prompt/配置/测试/设计文件已恢复Git可见性，docs/test产物和Python缓存仍忽略。文档同步，保留其他Agent改动与原暂存区，不改提取行为、不运行模型/测试或写库，尚未执行提交。

- [x] Explain回复增加逐字缓冲：大块delta/completed不跳过动画，支持立即显示、停止冻结和减少动态效果；Markdown标题/列表/粗体/代码/表格正确渲染，浮窗按需分包。26项浏览器回归、typecheck/lint/build及桌面/窄屏截图通过；未改后端、调用真实模型/数据库或操作用户8000/8100服务。见 `docs/apps/web/changelog/2026-10-17-explain-typewriter.md`。

- [x] 排查来源解释503：8000正常，用户仅启动提取Worker、8100未监听；已补启动src.extraction_main HTTP（inline Worker=false），后端AgentBridge探活成功、Explain路由存在、鉴权后空输入422验证通过。配置标志/内部令牌一致，未改业务数据或调用模型；后台PID/日志在.runtime/explain-http，现有Worker保留。见Agent共享宿主交付中的启动排障记录。

- [x] 接入Explain独立浮窗：行/页悬停与触屏入口、自动解释/流式追问、淡色可展开工具结果及原页/跨页图纸；8000 JWT代理→8100共享宿主，Pydantic/OpenAPI/TS生成同步。94项后端/Agent离线、22项浏览器回归、截图/typecheck/lint/build及13源码strict mypy通过。未调用真实模型/数据库或重启既有服务；加载新API/宿主后使用。见 `docs/apps/web/changelog/2026-10-17-explain-panel.md`。

- [x] Explain Agent增加search_connections/view_drawings：兼容行入口，支持来源/目标页、原理号、起终点端子精确组合查询、分页/覆盖情况、关联图纸及按需视觉分析；LangGraph原生工具循环、身份隔离、查询/图片摘要刷新。51项Explain/共94项相关离线回归、13源码strict mypy与Ruff通过；额外旧Supervisor有2项缺失历史Prompt失败，未改旧链路。未接前端/挂载共享服务、未调用真实模型/数据库或写库。见 `docs/service/agent/changelog/2026-10-16-explain-retrieval.md`。

- [x] 完成本地extraction隔离及ZH跨页列区域高清实验：新增文件本地忽略、已跟踪改动本地提交保护，保留191文件快照；显式--profile zh_crop启用，原zh整页保留。初扫不变、目标局部图替换整页、坐标回映原图，单次补全/原像素预算保持。3源码strict mypy、4文件Ruff、5文件语法、四Profile绑定、46摘要及1/5案例Schema/路径、CLI帮助与裁剪预览核对通过。用户自行跑提取测试，未运行pytest/Fake VLM/真实模型或写库，不提交。见 `docs/service/agent/changelog/2026-10-16-zh-completion-crop.md`。

- [x] 在现有 `src/agent/explain_agent` 完成独立LangGraph：只读三表、原页/跨页图片与证据路径、规则冻结/回退、多轮/版本刷新及字段差异；Python、受限CLI、宿主注入身份的可挂载HTTP/SSE已提供。20项模块、连同网关/Harness/Server共59项离线测试、Ruff和9源码strict mypy通过，CLI帮助与资源打包检查通过。未挂前端/共享服务、未调用真实模型/数据库或改提取规则/执行旧清理。见 `docs/service/agent/changelog/2026-10-16-explain-agent.md`。


- [ ] 清理旧Supervisor、纠错/自完善/评测Agent及独占Graph/API/编排/失效脚本：依赖核对及92文件审阅清单已整理，自动审批拒绝大范围删除与入口改写，尚未执行代码删除/入口停用，等待用户明确确认范围。保留独立提取、用户现有改动、样例/结果与共享基础；仅新增方案/开发边界文档，不操作数据库或重启服务。见 `docs/service/agent/independent-agents-cleanup-plan.md` 与 `independent-agents-retirement-inventory.md`。

- [x] 为三表结果增加start_terminal_coordinates/end_terminal_coordinates：沿用Agent{x,y,pdf_page_number}，可空JSONB/校验/失效清理与API/前端类型同步。20项后端、Web检查、真实本地SQL/HTTP坐标及CRUD兼容验证通过，migration已部署，合成数据清理；不重跑Agent或实现高亮。见Server坐标记录。

- [x] 按用户精简的ZH manifest保留1组003C01初扫、5组补全/负例及4图；删除独占未引用6图/12JSON，清理顶部图片目录、更新manifest v13/资源checksum/README及两处测试资源引用。剩余文件引用完整、Schema/路径/摘要/语法与diff静态核对通过；Profile保持2.1.1，不运行测试/模型、不写库。见Agent C01样例清理记录。

- [x] 移除登录后独立项目目录页：有项目直达首个项目，无项目显示完整空工作区/上传/规则入口；重命名删除保留在侧栏。13项浏览器与类型/lint/build通过，桌面/窄屏截图核对；不改数据库或提取规则。见Web工作区入口记录。

- [x] 完成本地ZH2.1.1跨页读取修正：上下文v2不传起点端子/坐标/方向描述，匹配任意边界回指后分别读接口/针脚，目标缺失时只按唯一来源页PDF证据核对；强化初扫引用拆分、接收段与直接放线段说明。5初扫/9补全/10图、manifest v12/checksum及回归文件同步；语法/Schema/路径/7源码类型/CLI加载静态核对通过，修改核心与新回归lint通过。未执行测试或模型、不写库或覆盖结果，实际效果待新目录复测。见Agent跨页读取记录。

- [x] 适配三表前后端数据管理（2026-10-16）：项目/规则引用/PDF登记、JSON图纸预览、批次线表与事务行级CRUD改接新表；上传不触发Agent。OpenAPI/TS同步，14项后端/10项浏览器、类型/lint/build、真实本地Auth/Storage/CRUD验收通过，合成数据清理；RPC迁移已部署。用户重启8000后刷新，提取链路后续接入。见Server/Web交付记录。

- [x] 完成本地ZH2.1.0目标图定向补全：Profile控制图片模式，state携带来源业务页/Object Loc/信号名并投影精简任务，初扫方法不变；ABB/XMZ保持双图。5初扫/4补全案例、manifest v11/checksum与回归文件同步；14份Python语法、9源码类型、路径/Schema/三模板绑定与CLI帮助静态核对通过，无新增lint。按用户要求未运行测试/模型，不写库或覆盖结果；精度/耗时待用户新目录复测，见Agent目标图补全记录。

- [x] 完成实际图优先像素预算：先保留输入，再压缩Few-shot至默认768px下限、整对减少案例；实际图自身超预算才缩小。配置/删例metadata/缓存指纹与回归文件同步，分组CLI额外预缩放默认0。7份Python语法、配置、两CLI加载、预算模块类型和模块/回归文件lint通过；按用户既有要求未运行测试/模型，不写库或覆盖结果。见Agent输入图优先记录。

- [x] 统一ZH/ABB/XMZ主表14列及端子坐标：公共Graph/原生主表/本地脚本复用表头、行映射及ZH默认样式；ABB1.1.4/XMZ0.1.2同步通用坐标说明和图像expected，29/34个已知示例端点坐标与物理页、Schema/checksum/路径核对通过。13份Python语法及三模板只读绑定通过，对比HEAD无新增lint；离线回归文件已补但未运行，不跑真实模型、不写数据库或覆盖旧结果。见ADR-0019及统一表格记录。

- [x] 修正ABB输出契约：所有模板注入共享JSON Schema，ZH专属语义保持隔离；本地PDF入口以文件TraceStore保存原始响应/finish_reason/用量与图片metadata，JSON重试带位置，明确length且无完整JSON时停止。9份Python语法、ABB只读绑定及Schema静态核对通过，对比HEAD无新增lint；相关离线回归已补但未运行，不调用模型或写数据库，旧失败响应不能补回。见ABB输出契约修订记录。

- [x] 补齐公共提取适配器请求图片控制：实际图默认2048px、请求案例/实际图合计600万像素，等比例缩小、不改原图；配置、发送尺寸metadata、本地调用日志及离线回归文件同步。8份Python语法、默认配置与diff检查通过，新增文件lint通过且对比HEAD无新增lint；保留既有9项。按用户既有要求未运行测试/真实模型，不写数据库，实际patch预算与识别质量待用户复测。见模型图片预算记录。

- [x] 更新本地ABB1.1.3小圆圈放线/大圆圈端子规则、同段双标记合并、数字或完整端子直接拼Sheet原理号；同步跨页说明、205/281真实图片expected、双图适配器和资源版本。1分类/3初扫/1补全路径、Schema/checksum/Python语法及只读Profile绑定静态检查通过，无注册错误；未运行测试/模型，不写数据库或发布。见ABB圆圈规则修订记录。

- [x] 补齐本地测试CLI规则切换：PDF/拆页入口支持--profile/--model并按adapter绑定策略，强制内存/本地资源、保留ZH默认参数；两入口--help、三种规则只读绑定及Python语法静态检查通过，命令和资源摘要同步。新增回归未运行，不调用真实模型/写库或生成新XLSX。见Agent本地Profile CLI记录。

- [x] 补齐003C01中间FC12组双图Few-shot：XA:11→003.C/31 XD10:1，保留160A及两端坐标；初扫五条引用已存在，增加目标图/task/expected、manifest v10/checksum及文档。静态路径/Schema/语法/绑定通过，不跑测试/模型、不写库。见Agent中间组记录。

- [x] 完成ZH2.0.5/manifest v9电流规则：端点冻结后沿同一相线查对应断路器Ie明确A值；003C01的XA:8～13六条160A、XD10:13～15三条80A，其余N/PE/控制仍空。Prompt/调用、expected/任务及checksum同步，静态路径/Schema/语法/绑定核对通过；未运行测试/模型或写库，实际效果待用户复测。见Agent Ie电流记录。

- [x] 完成ZH2.0.4/manifest v8：003C01整页替换接收负例，两组跨页改003C01→080C10/004C01，清理7张独占旧图及旧expected/task；端子归一化坐标/物理页贯通扫描、补全、JSON和14列本地XLSX。路径/Schema/坐标页号/checksum、13份Python与Node语法静态核对通过，未运行测试/模型、生成新XLSX或写库。见Agent坐标样例记录。

- [x] 完成本地ZH2.0.3起终点元件规则：同页附近→本端所在页Object Loc，跨页对应线路引用→附近→本端所在页Object Loc；可选source_component只补元件元数据，不改起点端子/原理号。同步Schema、Prompt/调用说明、四份初扫/两份补全expected、manifest v7/checksum及文档；静态路径/Schema/语法/绑定检查通过，未运行测试/模型，不写库或覆盖结果。见Agent元件优先级记录。

- [x] 按用户明确授权在本地supabase_db_zhenghua_test创建三张新业务表，删除截图18张旧表/1个旧视图；两次事务演练及正式提交，所有者/跨用户/匿名RLS、页级唯一键/版本触发器通过。Agent/Auth/Storage数据摘要不变，迁移登记完成，旧数据未迁移；应用仍待适配。见Server实际清理记录。

- [x] 提供三张精简提取业务表创建SQL及ADR-0018：规则引用、项目、扁平连接结果，新增表名/所有者RLS/页级幂等键；未执行数据库命令或测试，现有应用适配和数据迁移未实施。见Server SQL交付记录。
- [ ] 三表Agent正式提取接入：前后端数据管理已完成，旧数据按用户决定不迁移、旧表已删除；后续接入上传后的渲染/分类/提取、图纸索引与当前批次发布、逐页结果持久化和任务恢复，不恢复旧业务表。

- [x] 对齐本地XMZ大车卷盘0.1.1规则：修复Profile/样例资源引用，采用放线标记和最近端子边界，expected仅保留图片可读事实；同步适配器、程序端子排及文档。2组分类/5组初扫/2组补全的路径、Pydantic Schema、checksum与Python语法静态检查通过，Profile只读加载无错误；按用户要求未运行测试/模型，不写数据库或发布。见Agent XMZ图像事实记录。

- [x] 修复本地ZH测试脚本被无关Profile缺失资源阻塞：选定ZH仍校验，其他无效模板告警后跳过，失败日志显示具体Profile原因。只读资源绑定确认ZH2.0.2及当前Prompt有效；新增两类回归但按用户要求未运行pytest/提取/真实模型，不写库或覆盖结果。见Agent本地Profile隔离记录。

- [x] 明确ZH初扫顺序：先定位放线标记，再沿两侧寻找最近端子/跨页箭头，最后按同段箭头判断方向；Prompt、调用指令、规则/checksum与变更记录同步。按用户要求未运行测试或模型，实际效果待用户复测；不写数据库、不覆盖结果。

- [x] Stage2测试脚本默认页面目录改docs/test/pages，索引改实际位置docs/test/pages/agent/drawing_index.json；说明和模块记录同步，未运行测试/模型、不覆盖结果。

- [x] 迁移61份两阶段提取源码到`services/agent/src/agent/extraction_agent`，只调整导入/patch目标、资源/入口/包引用；共享包按用户布局改为src。254份Python静态AST比对无非引用实现差异，116份资源字节不变，3份路径/校验和元数据同步；.env仅改AGENT_PROFILE_ROOT目录引用。未运行业务测试/模型/数据库/服务，不覆盖旧结果。见ADR-0017和Agent迁移记录。

- [x] 同步ZH expected与2.0.2 Prompt：C01完整XD1端子/排号、C02可见元件描述、FO2补全区分设备代号和实际排号；manifest v6/provenance和文档更新。只改样例，不运行测试/模型，不写库或覆盖结果。见Agent expected同步记录。

- [x] 清理ZH样例中的regression_cases、两份expected及两张独占图片和空目录；manifest v5、provenance、测试引用与文档同步。保留5组初扫/2组补全，不运行测试、不写数据库，用户已有stage3删除保留。见Agent样例清理记录。

- [x] 按用户2026-10-14新口径完成本地ZH2.0.2规则/后处理修改：精简两份Stage2 Prompt，按放线段两侧直接端子提取、补齐同排X/XD数字端子，端子排仅由程序映射，保留电流约束；新增M23原图及八条用户确认expected、manifest v4/checksum和既有测试预期同步。用户要求自行测试，本轮未运行测试/真实模型/脚本，不写数据库、不发布、不覆盖旧结果。见ADR-0016及Agent变更记录。

- [x] 微调 Supervisor 为专业电气图纸与线表助手：CHAT 公开回复流、日常无确认卡片、任务先说明后卡片，提取只使用已上传 PDF；77项 Agent/Server离线测试、21项浏览器夹具回归、Web类型/lint/build、修改文件Ruff与3源码strict mypy通过，桌面/窄屏截图已检查。契约6/checksum与文档同步，Server OpenAPI导出无差异；未调用真实模型、写业务数据库或重启现有Agent，实际服务需加载新代码。见 `docs/service/agent/changelog/2026-10-13-supervisor-chat.md`。

- [x] 补充 Web、Server/API、Agent README 的 Windows PowerShell 本地启动指令、依赖/配置准备、端口、健康检查和同进程 Worker；启动命令语法与入口路径静态核对通过。只改文档，未安装依赖、启动服务或写数据库。

- [x] 基于本地002.C/002.M原图核对完成ZH2.0.1：方向契约/缺失降级、原始引用解析、端子身份/同页/分支/器件定义规则与实际图片Few-shot；40项冒烟、7项接口/兼容边界回归、Ruff与8文件strict mypy通过，公共Schema不变。保留旧结果，不写数据库、不发布、不调用真实模型；真实效果尚未复验。见 `docs/service/agent/changelog/2026-10-13-zh-stage2-quality.md`。

- [x] 核对1002001693大车卷盘25页PDF与XLSX，新增本地 `zh_gantry_reel@0.1.0` experimental Profile/三类Prompt各两组图像样例、可逆页标/引用适配及字段级代表差异；5项离线资源/接口回归通过。未上传/写数据库/改既有ZH或ABB/调用真实模型，expected仍待工程确认。计划见 `docs/service/agent/zh-gantry-reel-profile-plan.md`，说明见 `zh-gantry-reel-review.md`。

- [x] 大车卷盘规则及配套代码已定向同步回 E 盘项目；保留分支/既有测试脚本/未提交改动，15项离线测试通过，不写数据库、不发布规则。

- [x] 完成本地 `run_stage2_groups.py` 及标准 12 列 XLSX 导出（色标空）：真实 002.C/002.M 12 页/121 条、31 条待复核，结果位于忽略的 `docs/test/run_stage2`；14 项离线冒烟、Ruff 与 XLSX 结构/视觉检查通过。模型准确标识覆盖、双图请求缩图与未知页 0→null 兼容已处理；未连接/写数据库、上传/发布/改 `.env`/重启服务。字段级准确率未验收，见 Agent 执行记录。

- [x] 在 `codex/stage2-page-workflow` 完成 Stage 2 独立逐页 LangGraph、内部双图补全/完成页保存、移除独立 Stage 3、ZH 2.0.0 规则和纠错/契约迁移；10 项离线冒烟、修改文件 Ruff/语法检查通过。未写真实数据库/部署 migration/发布规则/重启服务，真实字段质量未验收。计划见 `docs/service/agent/stage2-page-workflow-plan.md`，交付见 Agent changelog。

- [x] 修复 Stage 2 页码类型兼容：统一将模型返回的 unit/connection `source_drawing_pages` 数字转换为字符串，保留非法结构校验；新增回归测试，4 项跨页状态测试与 Ruff 通过。旧失败 run 不重试，用户重载 Agent 后重新提交新图纸。

- [ ] 兼容规则候选确认的重复 `/resume`：当旧客户端或 Supervisor 将“确认规则修改”误判为通用人工输入时，依据已有候选 artifact 强制走幂等直接发布分支，避免已确认 run 被错误标记失败；补回归测试并由用户重载 Agent 验收。

- [x] 2026-10-13 移除规则修改链路的模型评测/二次审核：归因建议一次确认后直接构建并发布包；旧候选接续、重复确认、原子审计/版本保护及前端/终端文案同步。Agent 默认测试、strict mypy/Ruff、18 项浏览器回归及 Web 检查通过；28 迁移空库/旧数据与合成发布事务通过，新增 RPC 已在本地部署。未发布 test0 候选、未调用真实模型/停止任务；用户重载后验收。见 ADR-0013。

- [x] 项目切换使用已知摘要保留 Header/目录/导航，仅中间加载数据；目录不随点击重拉，Server 按 created_at/id 固定顺序，详情更新只原位合并状态。17 项浏览器夹具、29 项 Server 默认测试、Web typecheck/lint/build 与加载中桌面/窄屏截图检查通过。Server 排序需用户重载服务，未停止现有服务。

- [x] 左侧项目目录单击文件夹/名称直接切换项目数据，当前项目箭头独立折叠，非当前项目箭头直接进入该项目；移除二次“打开项目”入口。17 项浏览器夹具及 typecheck/lint/build 通过，桌面/窄屏截图检查完成。

- [x] 2026-10-13 导航/搜索按容器水平居中；线表双击或行按钮原位编辑，Enter/行保存、Esc/行取消，冻结版本基线，失败保留草稿/幂等标识；原 PATCH/审计语义不变。16 项 HTTP fixture 浏览器回归、typecheck/lint/build 和桌面/窄屏截图检查通过。见 docs/apps/web/changelog/2026-10-13-centered-inline-edit.md。

- [x] 2026-10-13 工作台精简：新增端子换为最右加号；移除全部工作区按钮、项目概览及结果统计副标题；导航显示当前项目名；左侧项目可折叠且移除 PDF 中间行/文件名副标题；聊天移除当前阶段卡片。13 项 HTTP fixture 浏览器回归、typecheck/lint/build 和桌面/窄屏截图检查通过。见 docs/apps/web/changelog/2026-10-13-workbench-cleanup.md。

- [x] 2026-10-13 前端目录/悬浮聊天：图纸库项目→工作区→图片原地展开及懒加载预览；右下角按钮切换非模态悬浮聊天，隐藏后保留草稿/订阅、重新打开不重复任务。13 项 HTTP fixture 浏览器回归、typecheck/lint/build 和桌面/窄屏截图检查通过；未调用真实模型或修改数据库。见 docs/apps/web/changelog/2026-10-13-directory-floating-chat.md。

- [x] 规则库取消草稿使用门槛：三个增量 migration 已应用；所有登录用户可读非候选手工规则包，旧 draft 升 active，同 key 默认最新版本，候选隔离/回滚不误伤其他版本。ABB 1.1.2 已上传读回并以 `abb_native` 注册，Stage 1/2/3 Fake 链路、RLS 非创建者读取、27 个 migration 空库/旧数据重放通过。未调用真实模型或修改项目数据。

- [x] 完成图纸目录最终检查：空目录提示、跨工作区平铺/点击定位、桌面/窄屏截图；11 项 Playwright、Web typecheck/lint/build 通过。初次只读核对发现 ABB 旧包为 draft；后续按用户新决策迁移为共享 active 并新增 1.1.2。
- [x] 用户确认规则库与账号无关后改为共享读取；数据库用非创建者 authenticated 身份验证可见 ABB，浏览器不再依赖包创建者 UUID。

- [x] 修复候选评测 Stage 2 定位上下文：明确传递冻结目标的起点身份，不传正确终点/原记录答案；4 种同页/跨页、扁平/嵌套起点用例核验最终模型消息，32 项相关离线回归通过、1 项既有 ABB adapter 名称断言失败未改，Ruff/161 源文件 mypy 通过。不改数据库/规则包/运行服务，不调用真实模型；旧评测缓存与失败后新评测入口仍另行处理。见 Agent 目标定位修复记录。

- [x] 图纸库只展示当前项目图纸、不展示项目或工作区文件夹；规则库显示共享可用包，不再显示草稿/候选/已发布三态。AI Improvement 候选不属于规则库列表。

- [x] 精简 ABB 样本：Stage 1 一页、Stage 2 一张含 Q4 跨页连接的原页（示例答案范围明确）、Stage 3 一例原页+目标页；三个阶段各一案例。abb@1.1.1 草稿已上传私有 Bucket，18 文件读回核验通过；11 项相关离线回归/Ruff 通过。原图、旧远端包与生产绑定保留，见 docs/service/agent/changelog/2026-10-12-abb-resource-compact.md。

- [x] ABB 样本资源包：4 张标注图整理为 4 个 Stage 1、4 个局部 Stage 2、7 个 Stage 3 样例，独立 Prompt/manifest/expected/task 与来源说明完成；21 项离线回归通过，abb@1.1.0 草稿上传私有 agent-profile-assets，45 文件读回校验通过。不改 test0、active 包或运行服务，见 docs/service/agent/changelog/2026-10-12-abb-resource-draft.md。
- [ ] ABB 质量验收：`abb_native` 执行支持及 1.1.2 可用包已完成；仍需工程确认 expected 与原理号优先级，并运行真实图片字段级回归。无需再做草稿发布操作。

- [x] 规则库包管理实现：基于共享可用模板新建、人工确认后 Bucket 直接注册、创建者删除/停用并保留历史引用；后续已由 ADR-0012 取消手工包草稿/发布步骤。API/Web/动态注册同步，未调用模型、不改 test0、不停止服务。
- [ ] 规则包交付验收：用户重载 Agent/Server 后验收真实 Bucket 创建/停用；修复本机 node_modules 读取权限后运行自动 OpenAPI 类型生成、Web lint/production build。本轮这些检查受 EPERM 限制，生成类型暂按已导出的 OpenAPI 手动同步。

- [ ] 工作台剩余验收：真实 Bucket 三阶段资源与图纸索引已通过；用户已授权使用现有 8100 和一次性项目调用真实模型。上传/检测/人工确认后的三阶段已成功，继续在同一临时项目验证纠错/人工确认/归因并清理；不停止用户任务，不改 Schema/test0。

- [x] 规则候选评测/审核/发布代码：冻结固定正例/负例与 accepted-feedback 目标，三阶段实际调用、持久案例/报告与断点复用，服务端 receipt/gate、两次人工确认和不可变 Bucket 发布；纯 HTTP 终端入口。49 项离线测试、160 源文件 mypy/Ruff 通过，真实候选只读预检 9 案例通过。无 migration/模型调用/线上发布，真实评测和审核/发布验收待用户执行，见 docs/service/agent/candidate-release-plan.md。

- [x] 修复规则补丁 JSON 解析：完整 JSON 优先、仅识别真正外层 fence，保留文件字符串内嵌代码块；新增纯 JSON/外层包装/前言三类回归，31 项相关测试与 158 源码类型检查通过，实际失败 Trace 只读重放通过。未调用模型/恢复任务/改库/发布规则，真实恢复待服务重载。

- [x] 修复 ProfilePatchBuilder 输出契约：只读 Trace 确认失败为 ProfilePatchModelOutput invalid_json；动态注入 Schema，明确纯 JSON、转义、完整文件替换与包相对路径；11 项相关离线回归通过。未重提取/提交已完成修订、未调用真实模型或发布规则；真实恢复待重载服务。

- [x] 修复独立提取审校脚本：缺失跨页页码保留待复核、循环引用检测；11 项离线回归通过，说明快照变化，未调用真实模型。
- [x] 修复独立审校对账：模型返回 matched 但缺少 connection_id 时降级为 needs_review，避免中断整批；离线回归覆盖。

- [x] 按用户确认完成单条端子新增/删除：既有表 Server 原子事务、权限/revision/幂等/before-after、稳定其他 ID/线号/代次与 Web 入口；24 项默认 API、5 项 HTTP 浏览器夹具通过，真实 Auth/DB/Storage/API/浏览器增改删/双图/越权/过期/冲突/重放/审计失败回滚通过。一次性项目/对象/账号及自建进程清理，不改 test0/Schema/Agent 核心。

- [ ] 真实工作台接入（不改数据库/Agent 核心）：Server JWT/项目权限、项目树/线表 CRUD/图纸索引/私有资源包接口；Web 页码与线号分组、原页/跨页下方预览、编辑、规则资源面板、Agent 流式上传/纠错、可缩放布局。执行计划见 docs/service/server/workbench-integration-plan.md。
  - [x] Server/Web 基础接入与 OpenAPI 类型；21 项 Fake API、5 项 Playwright 夹具、Ruff/mypy/lint/build、真实库只读与既有修订 RPC 回滚验证。
  - [x] 真实 Auth 登录/续期、表格增改删与双图验收；事务失败回滚、权限/过期/幂等检查，临时数据清理。
  - [x] 真实账号浏览器验证 Bucket 三阶段 Prompt/样例图片/描述/expected、资源链接刷新和图纸索引。
  - [ ] PDF/纠错真实浏览器全链路验收：用户授权后上传/检测/确认与三阶段落库成功（5 页/13 连接，约 226 秒）；浏览器进程退出，纠错/确认/归因尚未验证。已有一次性项目可续跑，不重提取；自动审批服务模型权限 403 导致续跑命令未执行，详见 Server 联调记录。不停止用户服务。
  - [x] 流式交互收尾：最终确认提示可见、阶段单卡片更新、等待/失败展示、断线重连、StrictMode 首次检测取消和登录重复续期修复；补齐共享字段编辑、图片链接刷新、上传完整响应契约。写入真实联调已完成，会话全链路另验，不改 Agent 核心或 Schema。
  - [x] 完整性核对：规则 manifest 样例、纠错确认/归因、候选授权与 Agent 401 边界；端子增删和临时数据授权已落实。证据见 docs/service/server/workbench-completion-audit.md，完整 Agent 验收仍未完成。

- [x] 准备 test0 三条混合纠错注错样例：PDF 核对 XD3:251→2、XD3:260→1、006.M/1 XD3:113→006.C/1 X3:1，仅将最新代次三条 end_terminal 改为999；标记人工注错并备份原值/预期/消息到忽略的 runs/test0-mixed-prepared-001，revision 1→2。未修改规则、起点、跨页状态/引用，未调用模型或重启服务。

- [ ] 用户混合纠错及规则发布人工验收：`2.纠错agent/run_acceptance.py` 检查混合修订/归因，规则问题使用 `--expect-rule-issue`；一次确认直接启用。既有候选使用 `run_rule_release.py` 确认发布，不再评测，不重复注错或纠错。

- [ ] 用户重载 Agent 后验收原位纠错：本地 `20261011020000` 和契约 V3 已部署，直接答案/Stage 2/3 共用稳定 ID 提交；先只对当前最新行注错，确认后检查同 ID 更新和 revision，历史不清理、现有服务未重启。

- [x] 修复案例 A 确认后的 409：只读确认版本 2 已 accepted，错误来自归因 run 把 feedback ID 当成 PDF ID；改用原纠错 run 的 source document，冻结 Profile，归因启动失败明确返回已提交结果；5 项相关回归/strict mypy 通过，未重复提交修订或重启服务，待用户同 proposal 幂等补启动。

- [x] 修复案例 A 的 Supervisor MODEL_SCHEMA_INVALID：实际模型输出数字页码及 start_terminal 导致校验失败；增加方向查询、编号整数归一化和动态输出 Schema，23 项相关离线测试/strict mypy 通过；修复后只读模型路由和唯一匹配验证通过，未分派工作流或修改线表，服务待用户重载。

- [x] 编写纠错批次与 Bucket Profile 资源包修改方案：保留跨页 Stage 2→Stage 3，复用 test0 手工注错/自然语言输入验收，不新增终端验收脚本；本轮仅文档、不修改代码/数据库/规则包。详见 `docs/service/agent/correction-agent-refactor-plan.md` 与 ADR-0009。
- [ ] API/Worker 启用 `AGENT_PROFILE_PACKAGES_ENABLED=true` 并由用户加载新代码，然后进行 test0 手工纠错验收；数据库迁移和 ZH bootstrap 包发布已完成，现有服务未重启。

- [ ] Gate B 真实模型人工验收：使用已有 Auth 用户 UUID、真实 PDF 和人工 baseline，通过显式开关/终端确认运行 `1.3stage/run_acceptance.py`；接口与 Fake 验收已完成，准确率尚未验收。

- [x] 从保留的 `.git-new` 恢复本地 Git 历史和 origin，整理当前源码、文档及版本化 Few-shot 资产，排除密钥、缓存和提取运行产物。

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

- [ ] 补齐纠错/改进（protocol 1）run 的过期 RUNNING 接管和 fenced 写入；当前仅已持久 item 能在重新执行时复用，不声称自动故障恢复。

- [ ] 初始化 monorepo 根配置。
- [ ] 创建 FastAPI 新模块目录和兼容适配层。
- [x] 设计并评审 Supabase 新迁移和 RLS。
- [ ] 用真实 API 替换 mock 数据。
- [x] 将 Agent runtime/checkpoint 迁出 `frontend/public`。

## Agent

- [x] 实施阶段持久化 Gate A：真实数据库/Fake VLM 验证阶段屏障、RUNNING 接管/fencing、权威集合、最终收尾、树发布、退避/取消及独立 Worker 进程空缓存续跑；不包含 Gate B。
- [x] Gate B 接口与 Fake 验收：业务上传/Profile 确认/原子入队、持久 Worker、HTTP 查询/SSE、`1.3stage` 纯 HTTP 终端脚本；真实模型人工验收另列。
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
- [x] 完成 ABB 三阶段独立 Prompt、图片 Few-shot 和 Expected JSON 草稿；工程确认与真实模型验收另列。
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

- [x] 修复Explain口述预览但无确认按钮：只读确认新接口已加载、截图行无持久方案；真实回执后置校验、一次受控工具补调/明确失败、answer_reset撤回不实文本与API2.7.1契约同步。68项Agent、5项Server、19项解释浏览器、14源码mypy与Ruff/typecheck/lint/build通过；不跑真实模型或改实际线表/启停服务，需重载8000/8100后重发原请求。见 `docs/service/agent/changelog/2026-10-18-explain-preview-receipt.md`。

- [x] Explain线表修改工具：工作区/原理号精确范围，去端子前缀、整组起终点交换（含元件/描述/坐标/对应页码）、仅端子交换及字段赋值；先回答后逐行对照、用户确认Server原子写库、版本/完整范围/索引保护、幂等审计与前端刷新/恢复。58项Agent、27项后端、6项独立SQL、75项全量浏览器及6项后续定向、14源码mypy和Ruff/typecheck/lint/build/截图通过。本地已部署20261018020000，三表摘要不变；未调用真实模型或改真实线表，8000/8100待用户重载。见 `docs/service/agent/explain-edit-plan.md`、ADR-0033。

- [x] Profile三步创建与手动发布：静态模板/图片生成候选、表格确认/依赖失效/草稿恢复、私有不可变规则包及目录/预览/Worker加载；47项Agent相关（后续7项复验）、29项后端、2项独立SQL、51项浏览器、16源码strict mypy与Ruff/typecheck/lint/build及截图通过。未调用真实模型或发布真实规则，迁移/服务未部署；原Supabase临时库权限测试触发PG自动恢复及清理情况见Server交付记录。见 `docs/service/agent/profile-wizard-plan.md`、ADR-0028。

- [x] 2026-10-17完成独立profile_agent：复用提取Schema的模板填充、规则/样例/原图诊断、具体建议确认后编辑、明确指令直接编辑草稿、Expected确认和校验包输出；SDK/CLI/可注册Router与持久草稿/审计完成。33项新测试+3项Registry回归、13源码strict mypy和Ruff通过。未接规则页/正式发布、未改Explain/共享宿主、未调用真实模型或写Supabase；见Profile Agent交付记录。

- [x] 2026-10-16修复Worker启动404：仅将20261016020000部署到本地zhenghua_test库，原函数/桶配置备份在被忽略的.runtime/migrations，迁移历史同事务登记；只读HTTP核对四个RPC可见及8000 API为2.1.0。未领取任务、未重启服务、未调用模型；用户重新运行Worker。

- [x] 2026-10-16接通上传入队、独立Stage1/2 Worker、逐页图片/分类/初扫/跨页补全发布与前端SSE刷新；程序统一生成review原因，支持租约恢复、稳定行ID和处理期只读。62项Agent、19项API、15项浏览器、两种隔离库迁移/事务场景及Web检查通过。未运行付费模型、未部署当前项目库或重启服务；启用见Agent/Server README。见ADR 0022和增量交付记录。

- [x] 修复 ImprovementDiagnoser 输出契约：system 动态注入完整 Diagnosis JSON Schema，明确字段/枚举且保留严格校验与端点兼容；24 项相关离线测试、全包 strict mypy 和修改文件 Ruff 通过。原三条修订已提交，未重提取/重新提交/注错，也未写数据库、调用真实模型或重启服务；用户重载后仅恢复失败的归因 run。

- [x] 修复混合纠错起点身份匹配：区分位置/设备/端子、保留稳定 ID 和起点，缺失/歧义/重复明确报错；Worker 记录安全异常类型和调用帧。33 项相关离线回归、全包 strict mypy 和修改文件 Ruff 通过，失败任务 Stage 2 产物只读重放通过；未改数据库或规则、未调用真实模型、未重启服务。用户重载后用新会话重跑混合验收。

- [x] 第一个混合纠错终端脚本：纯 HTTP 输入/SSE/阶段与模型输出、人工确认、原位数据核对、规则无问题/证据不足/拒绝意外候选分支、逐步落盘和只监看模式；只读观测接口过滤私有推理并限制用户范围。离线 Mock 流程/相关回归、strict mypy/Ruff 通过；后续已补充 `run_rule_release.py` 接续候选发布链路。

- [x] 原位纠错（ADR-0010）：当前集合内连接/单元/证据 ID 和线号保持稳定，revision/record_version+1，before/after 留在 feedback，proposal receipt 幂等；内存/Supabase、确认消息、分页契约已同步。17 项相关离线测试/strict mypy/Ruff 通过，真实数据库合成回滚验证权限/幂等/过期拒绝/批次原子性，本地 migration 已部署，不修改 test0 的现有值、不重启服务。

- [x] 部署纠错资源包：本地 `zhenghua_test` 事务应用并登记 `20261011010000`，发布与 test0 checksum 一致的 ZH bootstrap；29 个包文件下载校验通过，7 张图片签名 URL 可生成，匿名元数据读取为 0 行，原线表摘要不变；修复 void RPC 空成功响应解析。未运行真实模型、未更改服务开关或重启服务。

- [x] 纠错方案代码基础：混合 CorrectionBatch、统一 proposal 提交、Stage 2→Stage 3 持久阶段调用、归因证据上下文、自包含 Profile 资源包及候选发布/回滚适配器；26 项离线测试、全包 strict mypy/Ruff 通过。数据库部署、真实包上传、人工验收和非提取 run 接管/fencing 未完成，详见 Agent 实施记录。

- [x] Gate B 实现：阶段 0 临时附件与业务源 PDF 隔离、冻结 Profile/确认审计、原子 run/event/queue、published 树与版本化分页结果、阶段摘要/SSE 续传和纯 HTTP 脚本；113 默认测试、2 个真实本地 Supabase/Fake HTTP 场景通过，22 migration 空库/旧数据及原子失败回滚通过；真实 VLM 未运行、Web/JWT 代理未接。

- [x] Gate A：逐阶段提交/读库屏障、不可变模型项/清单、输入/结果/记录摘要、Worker fencing 与幂等 finalize；105 项默认测试通过、10 个真实 Supabase/Fake VLM 场景分批通过，21 份 migration 空库/合成旧数据验证通过；未调用真实 VLM、未重启既有服务。
- [x] 按六项评审意见修订持久化方案/ADR 至 V1.1：补齐 Worker 状态接管、上游权威集合、最终 receipt/finalize、未发布树/epoch、精确摘要/冲突语义和 Gate A/B；仅文档，运行链路未改。
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
