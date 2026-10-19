# Changelog

2026-10-19：已发布规则支持创建者修改目录显示名，主标题/上传选项/预览显示数据库名称，内部标识、版本、ZIP及项目绑定保持。新增鉴权PATCH/旧名条件更新，OpenAPI/TS同步；5项Server、16项浏览器及静态检查通过，无实际改名/模型/业务库/服务操作，重载8000刷新Web即可。见[Server](../service/server/changelog/2026-10-19-profile-display-name.md)、[Web](../apps/web/changelog/2026-10-19-profile-display-name.md)。

2026-10-19：三阶段确认后缺有效起点不再阻断规则发布，空端点保留且提示后续校验；ValidationIssue.severity、review_1.1.0、Server/OpenAPI/TS同步。13项后端和3项浏览器及静态检查通过，实际test修订9只读验证ready=true，未代发规则/调用真实模型或操作业务库/服务；重载8000/8100刷新Web即可。见[Agent](../service/agent/changelog/2026-10-19-permissive-publication.md)、[Web](../apps/web/changelog/2026-10-19-permissive-publication.md)。

2026-10-19：修复规则配置内部参数缺项导致DIALOGUE_INPUT_INVALID的中断；已上传图片可继续使用，缺来源在聊天中追问，候选仍需确认。去重40项离线及Ruff/mypy通过，无真实模型/草稿写入或业务库/服务操作；重载8100生效。见[Agent交付](../service/agent/changelog/2026-10-19-profile-dialogue-input-recovery.md)。

2026-10-19：按用户纠正，规则配置图片/PDF附件统一先暂存，点击发送/Enter才建草稿、上传和请求读取；支持补充说明、移除及Shift+Enter换行。去重25项浏览器及类型/lint/build通过，无真实模型/会话/服务操作，本次只需刷新Web。见[显式发送修正](../apps/web/changelog/2026-10-19-profile-explicit-send.md)。

2026-10-19：规则配置改为聊天引导，支持图片/PDF拖拽自动建草稿和读取、逐阶段公开识别链路、用户意见修正、确认后自动尝试下一阶段；界面移除阶段切换栏，发布仍需手动。PDF任意阶段抽样和4张分类图片契约同步，已提供样图可复用；39项Agent、5项Server、去重24项浏览器与静态检查通过。无真实模型/实际草稿/业务库/服务操作，需重载8000/8100刷新Web，见[ADR-0038](../adr/0038-guided-profile-authoring.md)、[Web](../apps/web/changelog/2026-10-19-guided-profile-authoring.md)、[Agent](../service/agent/changelog/2026-10-19-guided-profile-authoring.md)。

2026-10-19：规则会话删除改到下拉列表每行右侧，无需先恢复；打开与删除独立，删除其他会话保留当前编辑，支持键盘、外侧关闭和长名称省略。19项会话+2项登录/工作台浏览器及类型/lint/build通过；沿用已有API，本轮仅刷新Web，无真实会话或模型操作。见[Web交付](../apps/web/changelog/2026-10-19-profile-conversation-controls.md)。

2026-10-19：规则配置智能体支持确认删除已保存会话，已发布规则保留；上传PDF/图片合并为发送旁图标，原阶段/重试限制保留。Agent墓碑存储、Server鉴权DELETE/204、OpenAPI/TS同步，11项后端及17项浏览器和静态检查通过，未操作真实会话/模型或启停服务。需重载8000/8100刷新Web，见[Web](../apps/web/changelog/2026-10-19-profile-conversation-controls.md)、[Server](../service/server/changelog/2026-10-19-profile-conversation-delete.md)、[Agent](../service/agent/changelog/2026-10-19-profile-conversation-delete.md)。

2026-10-19：ZH2.3.0、ABB1.3.1、XMZ0.2.1完整资源包已存入私有project-assets并登记数据库，读回/15组消息比对通过；ABB/XMZ补丁号仅用于不可变包发布，不改识别内容。上传PDF选项和Extraction Skills仅从已上传数据库包获取，移除本地登记UI；旧项目和6条旧规则不改。静态、离线API及11张界面截图通过，无模型/提取调用，启用需重载8000刷新前端。见[Server](../service/server/changelog/2026-10-19-database-profile-catalog.md)、[Web](../apps/web/changelog/2026-10-19-database-profile-options.md)。

2026-10-19：用户确认重扫全量替换语义，整页/工作区删旧写新，局部仅更新选中行/字段；确认前保留旧数据，删除/新增及空结果明确预览。新迁移、能力门禁、并发/回滚/旧候选禁用及新行会话已实现并验证，本地三表摘要不变，未提交实际替换。见[ADR-0036](../adr/0036-rescan-scope-replacement.md)、[Agent](../service/agent/changelog/2026-10-19-rescan-scope-replacement.md)、[Server](../service/server/changelog/2026-10-19-rescan-scope-replacement.md)、[Web](../apps/web/changelog/2026-10-19-rescan-scope-replacement.md)。

2026-10-19：按用户要求统一ZH源码资源来源：prompts/zh维护Prompt/样例，profiles/zh配置引用并提供运行策略，resources仅在打包时生成。清理重复源码副本、旧补全文件及失效测试引用；模型输入/策略不变，静态及封装校验通过，未上传或运行模型。见[去重记录](../service/agent/changelog/2026-10-19-zh-source-cleanup.md)。

2026-10-19：正式ZH入口整理为zh2.3.0，完整沿用用户已验证的zh_crop2.2.1局部高清资源，全部资源自包含；旧命令/冻结包和运行策略保留。生成本地可校验ZIP，未自动上传或改项目规则；静态及资源/封装对照通过，未运行模型或测试。见[Agent记录](../service/agent/changelog/2026-10-19-zh-profile-consolidation.md)。

2026-10-19：Explain重扫按原页端子/元件识别方向纠正后的同一行，单条补全明确主图与辅助图角色，针脚定位冲突进入复核。25项Fake/Mock及静态/回放通过，任务前4行回放为4更新2新增；未调用模型或改当前7行，需Worker新代码/新任务验证。见[记录](../service/agent/changelog/2026-10-19-rescan-identity-evidence.md)。

2026-10-18：品牌更新为振华重工放线表提取系统，项目根范围支持全量正式线表13列XLSX导出（电压等级与端子排独立）；Explain可拖动，历史重扫按需查看，自动来源解释限制重扫工具。API2.9.0/OpenAPI/Client已同步，79项Agent、37项API、54项浏览器与静态检查通过，无数据库迁移或实际业务操作。见[ADR](../adr/0035-project-xlsx-export.md)、[Web](../apps/web/changelog/2026-10-18-project-export-chat.md)、[Server](../service/server/changelog/2026-10-18-project-export.md)、[Agent](../service/agent/changelog/2026-10-18-explain-request-modes.md)。

2026-10-18：图纸预览滚轮缩放/中键拖动，项目目录侧栏可收起；重扫按钮自动发送所选范围请求，候选仍人工确认。Explain图片按消息显示，支持原界面居中放大。65项相关浏览器及静态/截图检查通过，无后端契约或数据库变更。见[Web记录](../apps/web/changelog/2026-10-18-workbench-interactions.md)。

2026-10-18：Explain006M01失败复现为模型供应方发布检查点不可加载；共享网关将HTTP200 SSE中的error事件正确识别为模型服务错误，保留坏帧校验且不自动重试该错误。Explain给出对应安全提示，41项离线测试/Ruff/mypy通过；无实际线表、Profile或模型配置改动。见[根因记录](../service/agent/changelog/2026-10-18-explain-errors.md)。

2026-10-18：Explain失败提示区分模型HTTP/格式与数据服务错误，补脱敏终端日志；SSE连接200后仍可能返回error事件。zh_test/006M01只读取数正常，历史具体异常未留存，重载8100后重试确认。35项离线测试及静态检查通过，无真实模型/业务写入。见[记录](../service/agent/changelog/2026-10-18-explain-errors.md)。

2026-10-18：Explain新增原图与辅助截图重扫，复用提取核心和原Profile，支持行/页/工作区及零结果范围。前端准备/上传/粘贴、异步进度和候选对照，Server确认后CAS更新或新增，原行归属/ID不变、不自动删除。共享Worker且无新端口。92项Agent、27项API、11项独立SQL、27项浏览器与静态/布局验收通过，本地新迁移20261018050000已部署、三表摘要不变；未运行真实模型或提交真实业务修改。见[Agent](../service/agent/changelog/2026-10-18-explain-rescan.md)、[Server](../service/server/changelog/2026-10-18-explain-rescan.md)、[Web](../apps/web/changelog/2026-10-18-explain-rescan.md)。

2026-10-18：ABB本地1.3.0按实际导线追踪整页端点，模型分开读两侧标记数字，程序生成原理号并保留依据；57条整页适用连接/电流示例和接收端等聚焦参考。公共十四列/坐标、ZH/XMZ与旧规则包契约保持；仅静态核对，未运行测试/模型或发布写库。见[Agent记录](../service/agent/changelog/2026-10-18-abb-scan-evidence.md)。

2026-10-18：ABB本地包1.2.2统一补全Prompt和样例目录命名到ZH，历史原图/离线案例移到测试夹具，引用/摘要同步；提取规则、实际模型图片、Expected及十四列输出不变。仅静态检查，未运行测试或模型、不发布/写库。见[Agent记录](../service/agent/changelog/2026-10-18-abb-resource-layout.md)。

2026-10-18：按用户确认，PDF遍历正常结束统一显示处理完成，单页错误保留诊断，不再让整任务失败；历史EXTRACTION_PARTIAL在前端兼容显示完成，真正中断仍失败。静态及隔离浏览器核对通过，无数据库/API结构变更，不改历史业务数据。见[记录](../service/agent/changelog/2026-10-18-extraction-finished-status.md)。

2026-10-18：线表顶部提取未完成提示可通过右侧关闭按钮隐藏，保留任务失败状态和重试行为，新失败重新展示。前端类型/lint/build及隔离浏览器核对通过，无API/数据库变更。见[Web记录](../apps/web/changelog/2026-10-18-extraction-notice-dismiss.md)。

2026-10-18：按用户纠正，撤回整组端点调换迁移所属页/工作区的约定，固定记录归属和关联索引，仅交换端点/坐标对象，前端保留原筛选并禁用旧迁页方案。新迁移20261018040000已部署；实际4行按快照事务恢复006C01/006.C，ID、已确认端点/坐标和同项目其他行保持。相关70项Agent、5项API、10项独立SQL、25项编辑/预览浏览器及类型/lint/build/Ruff/mypy通过。见[当前设计与恢复记录](../service/server/explain-swap-origin-correction.md)；以下同日“跟随新页”的较早记录已被取代，删除修复保留。

2026-10-18：ABB本地1.2.1修正小圆点放线识别，覆盖母线输入、同段双标记、数字拼Sheet和无编号端子回退；初扫/补全保留完整端子身份。公共十四列/坐标、ZH/XMZ不变，未运行模型/测试或发布规则。见[Agent记录](../service/agent/changelog/2026-10-18-abb-marker-endpoints.md)。

2026-10-18：修复Explain整组调换后仍按旧来源页筛选的空表问题，确认后跟随新页/全项目并显示位置，行ID不变。按用户要求后续物理删行不留业务副本并清除相关方案，最小幂等回执保留；工作区已明确时Agent主动查询。新函数迁移本地部署、实际三表摘要不变，离线124项定向回归及类型/lint/build/Ruff/截图通过；未重跑真实模型或修改现有线表。见[联合排障](../service/server/changelog/2026-10-18-explain-delete-relocation.md)。

2026-10-18：提取任务单页初扫失败后记录并继续后续页，完整遍历后汇总未完成项；复用成功页缓存恢复，配置/存储/取消仍立即中止。不新增数据库/API状态，重启Worker后原项目重试。仅静态核对，未运行模型或操作现有任务。见[Agent记录](../service/agent/changelog/2026-10-18-extraction-page-failure.md)。

2026-10-18：修复Explain无真实方案却口述已生成预览、无确认按钮。无回执时撤回错误文本并受控补调一次，失败明确提示；不从文字制造可提交数据。新增answer_reset、API2.7.1及生成契约同步。68项Agent、5项Server、19项浏览器及类型/lint/build通过，无Schema变更、真实模型/数据修改或服务启停。见[记录](../service/agent/changelog/2026-10-18-explain-preview-receipt.md)。

2026-10-18：Explain新增线表修改方案工具，用户确认整组起终点连同元件、描述、坐标/页码一起调换，也支持去前缀与字段修正。API2.7.0确认事务、RLS/批次/版本/范围/幂等及审计，前端先回答后预览并刷新线表。58项Agent、27项Server、6项独立SQL、75项浏览器及后续6项通过，类型/lint/build和截图通过。本地仅部署新增结构20261018020000，三表摘要不变；未跑真实模型或改真实线表，待用户重载8000/8100。见[Agent](../service/agent/changelog/2026-10-18-explain-edits.md)、[Server](../service/server/changelog/2026-10-18-explain-edit-transactions.md)、[Web](../apps/web/changelog/2026-10-18-explain-edit-preview.md)。

2026-10-18：修复Profile辅助编辑将图片/用户结果证据按文本文件读取的问题，诊断与建议持久化共用来源校验；保留用户确认、修订和发布约束，历史工具错误可在新轮继续。EvidenceAnchor形状兼容，生成DTO/OpenAPI/TS字段说明同步，不修改已发布规则。验证及重载8100说明见[Agent排障](../service/agent/changelog/2026-10-18-profile-evidence-validation.md)。

2026-10-18：平台上传提取与本地脚本统一请求/结果契约stage2-script-aligned-v1，禁色标处理、模型Gateway和14列业务字段共用，补过滤前计数、请求指纹及ZH0列兼容。ZH Prompt/样例与2.2.1业务规则保持，4初扫/14补全消息及154条投影离线核对通过；未跑模型/pytest、不改旧任务或业务库，需重启Worker后新上传测试。见[Agent记录](../service/agent/changelog/2026-10-18-extraction-entry-alignment.md)。

2026-10-18：基于ProfileAgent扩展已有规则编辑，Extraction查看规则可双击修改或用旁侧聊天结合图纸/实际结果诊断，查看工具及diff后同意修改并发布新版。新版替换入口，旧包无引用才回收；API2.6.0及生成契约同步，新迁移已部署本地且未改业务内容。76项Agent、26项Server、2项独立SQL、59项浏览器及最终25项复验/静态检查通过。未调用真实模型或代发规则，需用户加载8000/8100。见[设计](../adr/0032-profile-resource-editing.md)、[Web](../apps/web/changelog/2026-10-18-profile-rule-editing.md)、[Server](../service/server/changelog/2026-10-18-profile-editing-replacement.md)。

2026-10-17：ABB1.2.0和XMZ（zh_gantry_reel）0.2.0提取对齐ZH结构：单来源样例、对应目标图补全与各自图框局部高清读取；分页、ZH业务规则、最终14列/整页坐标保持。原起点/电流冻结，未知端点留空。仅静态/图片预览核对，不运行模型/测试、不写库或发布。见[Agent记录](../service/agent/changelog/2026-10-17-abb-xmz-alignment.md)。

2026-10-17：ZH局部跨页补全升为zh_crop 2.2.1，拒绝将空对象默认成有效结果，使用已有最多两次校验重试并保留失败/视觉原因；同号N线按来源业务页和完整信号匹配，新增005C01两组对照，正常路径仍单图/单案例。初扫/坐标/数据库保持，静态核对完成，未运行测试/模型，效果待用户复测。见[Agent记录](../service/agent/changelog/2026-10-17-zh-completion-response.md)。

2026-10-17：修复Profile发布“数据操作失败”的本地部署缺口：补齐既有发布RPC/保护触发器及迁移登记，REST Schema已刷新，已上传包可复用；业务内容摘要不变，未代为发布规则。缺函数返回明确且安全的配置错误，26项后端和2项独立SQL及Ruff/mypy通过。用户在原草稿直接重试，详见[Server排障](../service/server/changelog/2026-10-17-profile-publication-missing-migration.md)。

2026-10-17：Profile规则发布的负例改为可选输入，取消缺负例拦截并同步聊天/表单提示；已提供的负例继续校验、打包和使用，阶段确认等其余校验保留。34项Agent离线、17项浏览器及类型/lint/build、Ruff/mypy通过。未发布真实规则或操作用户服务，需重载8100后恢复对话。见[记录](../service/agent/changelog/2026-10-17-profile-optional-negative.md)。

2026-10-17：修复Profile换原页时描述指向新图、实际初扫仍使用旧图而触发NO_CROSS_PAGE_TASK的问题。新原页先生成并重新确认初扫，后续反馈按图片来源隔离，补全前核对实际引用；公开契约/数据库和发布条件不变。29项Agent离线回归、1项浏览器冒烟及静态检查通过，未改实际草稿或启停用户服务，需重载8100。见[交付](../service/agent/changelog/2026-10-17-profile-source-replacement.md)。

2026-10-17：修复Profile用户指出“终点就在本页”后仍反复确认/索要目标图的问题；允许补全阶段使用原图回到初扫生成修正候选，保留分类并按依赖重新确认。24项相关Fake/Mock和11项浏览器回归、类型/lint/build通过；公共API/数据库未变，未修改实际草稿或调用真实模型，需用户重载8100。见[ADR-0031](../adr/0031-profile-scan-correction.md)。

2026-10-17：Profile模型失败不再被统一提示隐藏，增加8100终端日志、私有响应诊断、前端错误码/编号和GeneratedAnswer完整Schema。9项新诊断及现有Profile回归、10项聊天浏览器和类型/lint/build通过。只读确认第一阶段与样图已保存，历史失败未留响应，实际模型根因/成功复试仍待用户重载8100后验证。见[记录](../service/agent/changelog/2026-10-17-profile-model-errors.md)。

2026-10-17：规则创建第一阶段可上传PDF自动随机取两页，Agent对照推测分页并分别建立Expected；第二/三阶段仍需用户提供图片。只保留抽中样图和来源元数据，原PDF及其余页不落盘，无需清理全册缓存。新增API2.5.0代理，无新迁移；25项相关回归、33项原Profile及60项浏览器和前端检查通过。见[ADR-0030](../adr/0030-profile-pdf-sampling.md)。

2026-10-17：Profile规则创建改为Agent引导聊天，支持文字/样图追问、三个阶段的读图结果与公开连接依据、纠正后确认保存规则/Expected及持久对话恢复。新增8000 API2.4.0鉴权SSE，8100复用既有阶段机制，发布仍手动；原表单保留兼容。57项离线浏览器及相关Fake回归、类型/lint/build通过，无新增迁移，未运行真实模型或操作用户服务。见[ADR-0029](../adr/0029-profile-conversation.md)及[Web交付](../apps/web/changelog/2026-10-17-profile-conversation.md)。

2026-10-17：Profile三步创建与手动发布完成代码接入，API 2.3.0；固定阶段模板、图片生成Expected、表格确认与草稿恢复，Server发布私有固定版本并接通目录/预览和Worker。47项Agent相关、29项后端、2项独立SQL和51项浏览器通过，16源码strict mypy/Ruff及前端检查通过。未调用真实模型、未发布真实规则或部署业务库迁移，目标Supabase环境测试异常及清理已记录。见[Agent](../service/agent/changelog/2026-10-17-profile-wizard.md)、[Server](../service/server/changelog/2026-10-17-profile-publication.md)、[Web](../apps/web/changelog/2026-10-17-profile-wizard.md)。

2026-10-17：图纸预览模式新增线表/图纸拖拽调宽、键盘与双击复位，修复缩放百分比和长标题溢出；45项离线浏览器及前端检查通过，仅前端变更。见[Web记录](../apps/web/changelog/2026-10-17-preview-resize.md)。

2026-10-17：按用户指定，智能体中心三个Agent的展示版本统一为1.0.0，Skill保留实际规则包版本；仅前端变更，详见[Web记录](../apps/web/changelog/2026-10-17-agent-center-preview.md)。

2026-10-17新增用户菜单“智能体中心”及三Agent卡片，提取规则作为zh_extraction等Skills迁入；默认全量线表铺满，按需五列压缩并在右侧上下展示原页/目标页及端点坐标，移除线号显示/底部图纸。44项浏览器与前端检查通过，后端及数据契约不变。见[Web交付](../apps/web/changelog/2026-10-17-agent-center-preview.md)。

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
