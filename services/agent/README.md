# Agent Service

2026-10-20 Explain的MODEL_SCHEMA_INVALID细分schema_validation，并输出脱敏Schema字段路径/错误类型/计数；不存模型原文、不放宽校验或自动重试。仅重载8100后对未来错误生效，旧c24fb14e未保留具体字段、不能还原，见[记录](../../docs/service/agent/changelog/2026-10-20-explain-schema-diagnostics.md)。

2026-10-20 Explain明确重新识别时不能以“正在读取”正文结束：本轮回执门禁/受控补调、规划正文不作进度和动作事实精简，兼容不支持required的服务。仅重载8100再发送，无本轮8000/Web/Worker或迁移变更，见[交付](../../docs/service/agent/changelog/2026-10-20-explain-action-completion.md)。

2026-10-20显式目标页新增授权目录入队前校验：scope源工作区不继承到目标binding，冲突返回实际目标工作区/PDF，Worker继续严格检查冻结目录；修复成功回执error:null误发失败事件。重载8100及实际重扫Worker后新建任务，无迁移/8000/Web变化，见[交付](../../docs/service/agent/changelog/2026-10-20-target-workspace-preflight.md)。

2026-10-20 Explain重扫规划与Worker路由按ADR-0042更新：新模型任务显式需求/范围能力校验，整页提取包含原理号和漏提候选，同页端点走本页识别、跨页保留冻结补全。先加载8000 API2.14.0，再重载8100/实际Worker，刷新Web新建重扫；rescan-v7不混用旧checkpoint。无迁移、无新增环境变量/服务种类，未改真实结果或生产Profile，真实质量待复试，见[交付](../../docs/service/agent/changelog/2026-10-20-rescan-requirements-routing.md)。

2026-10-20本地提取测试脚本现在从仓库根`agent_test/extraction_agent`加载代码及规则，目录整体Git忽略；正式Worker/服务和数据库已发布包不变。测试ZH2.3.1改为整页补全、加入002C03/原理号规则。副本缺失或正式模块已先加载时报错，启动打印实际路径；[初始化边界、测试命令与限制](../../docs/service/agent/local-extraction-test-runtime.md)。

2026-10-20 当前模型服务已明确拒绝required工具选择，Explain现仅对此400启用Pydantic JSON决策兼容，仍走原工具/权限/任务回执。重载8100后从失败消息重试，无新迁移、凭据或8000/Worker变化；169个场景分批离线通过，未跑真实模型，见[排障](../../docs/service/agent/changelog/2026-10-20-explain-tool-choice-compatibility.md)。

2026-10-20 Explain补调使用required工具选择和精简事实，本轮私有图片校验后实际进入视觉输入；其他Agent默认工具策略保持。重载8100并刷新Web重开窗口后发送，无迁移/8000或Worker变化。155项离线通过，当前供应方required支持待实测，见[记录](../../docs/service/agent/changelog/2026-10-20-explain-required-tools.md)。

2026-10-20 Explain修复只检索却宣称重扫queued：本轮真实任务回执校验、一次补调、失败关闭与缓存/历史隔离。无需新命令或迁移，重载8100后关闭再打开窗口并重新发送需求；原文字queued没有任务可恢复。127项离线回归通过，未运行真实重扫，见[记录](../../docs/service/agent/changelog/2026-10-20-explain-rescan-receipts.md)。

2026-10-19 Explain增加脱敏调用诊断，记录请求规模/工具轮次和安全上游分类，错误附诊断编号；文件位于忽略目录`.runtime/explain-diagnostics`，不保存图纸或对话正文。重载8100后正常失败请求才产生现场诊断，无额外模型调用/重试，见[记录](../../docs/service/agent/changelog/2026-10-19-explain-diagnostics.md)。

2026-10-19终点重扫支持逐连接target_bindings，用户指定的页号原样传递，冻结起点直接补终点；未定位目标不退回初扫，真实细节图受预算保护。输入契约3/缓存rescan-v6，需重载8000/8100及实际Worker后新建请求，旧实际任务不改写；见[交付](../../docs/service/agent/changelog/2026-10-19-rescan-explicit-targets.md)。

2026-10-19指定STS项目已启用“新重扫使用项目当前选定规则”（当前ZH2.3.0）：任务独立固定Storage包，不再优先旧批次包；其他项目默认历史规则保持。需部署迁移20261019030000并重载实际Worker后新建一轮，旧任务不能通过重试变成新版；rescan-v5隔离旧缓存。见[交付](../../docs/service/agent/changelog/2026-10-19-rescan-project-profile.md)。

2026-10-19修复已定位跨页但终点为空时关联页丢失：唯一目录目标页保留、端子仍待复核；重扫缓存契约rescan-v4，需重载实际Worker后新建任务并手动确认，不自动改写旧结果。见[交付](../../docs/service/agent/changelog/2026-10-19-rescan-target-page.md)。

2026-10-19主助手支持原理号范围/多编号、重复读取制止和数据修改候选＋规则诊断接续；已完成调用不能代替后续目标。需8000/8100同步重载再发请求，真实业务数据未修改，见[记录](../../docs/service/agent/changelog/2026-10-19-main-assistant-progress.md)。

2026-10-19修复主助手未调用工具却口述重扫成功：无工具终答增加短结构化执行核验、一次补调，启动确认只取真实回执。需重载8100及8000后重新发送需求；不自动补执行历史回复。见[修复](../../docs/service/agent/changelog/2026-10-19-main-assistant-receipt-guard.md)。

2026-10-19主助手首版已接入现有8100：业务检索跳转、Explain只读、重扫候选、Profile冻结包诊断和修改方案确认发布。重载8000 API2.11.0及8100后刷新Web；本地新增迁移已部署。沿用模型配置及AGENT_SERVER_BASE_URL回调地址，不新增端口。见[交付](../../docs/service/agent/changelog/2026-10-19-main-assistant.md)。

2026-10-19规则配置修复DIALOGUE_INPUT_INVALID：模型漏内部读取说明不再直接中断，沿用实际样图与用户上下文生成候选；真正缺来源会追问，首次失败恢复后可复用已存图片。重载8100后原页重试，或恢复会话输入继续；无前端/API迁移，未运行真实模型或修改实际草稿。见[排障](../../docs/service/agent/changelog/2026-10-19-profile-dialogue-input-recovery.md)。

2026-10-19规则配置主聊天移除阶段切换栏，支持图片/PDF先暂存、发送或Enter后建草稿和读图、逐阶段公开链路与用户确认后自动继续；手动多图分类逐图生成，PDF真实抽样图可复用，缺接线/目标图时追问。用户仍需确认候选并最后手动发布。需重载8100和8000后刷新Web，无新迁移/环境变量，未运行真实模型或操作实际草稿；见[交付](../../docs/service/agent/changelog/2026-10-19-guided-profile-authoring.md)与[ADR-0038](../../docs/adr/0038-guided-profile-authoring.md)。

2026-10-19三套资源包已发布到业务extraction_profiles/project-assets：ZH2.3.0、ABB1.3.1、XMZ0.2.1（后两者为上传补丁版本，来源本地1.3.0/0.2.0识别资源不变）。前端上传与Skills仅选数据库包；本地CLI仍读源码。初始化工具为 `scripts/bootstrap_database_profiles.py`，默认仅打包/只读预检，显式--apply才发布。既有Worker支持Storage包，重载8000刷新Web即可启用目录限制，未自动跑提取。见[交付](../../docs/service/server/changelog/2026-10-19-database-profile-catalog.md)。

2026-10-19重扫现按用户要求区分：整页/工作区all确认后替换整个旧范围，行ID/原理号或单侧字段仅修局部。候选包含完整删除/写入预览，全部页成功才生成，空结果需明确确认；旧版全量/旧缓存需新建任务。新迁移本地已安装且业务表未变，重载8000 API2.10.0、8100及实际Worker后刷新Web；inline方式无需另开Worker。不会自动清理已有结果，也未执行真实重扫。见[交付](../../docs/service/agent/changelog/2026-10-19-rescan-scope-replacement.md)。

2026-10-19正式ZH入口为 `zh@2.3.0`（振华电气图纸），已验证提示词/样例统一维护在 `src/agent/extraction_agent/prompts/zh`，profiles/zh只引用资源并提供策略；本地resources副本已移除，上传包的resources由现有打包器生成。新脚本统一使用 `--profile zh`，用户已移除zh_crop/history；已有冻结任务不改。最新本地未上传ZIP在 `.runtime/zh-source-cleanup/zh-2.3.0.zip`（仓库根目录），见[清理记录](../../docs/service/agent/changelog/2026-10-19-zh-source-cleanup.md)。

2026-10-19修复Explain方向纠正后的旧行匹配，补来源/目标/辅助图角色与定位冲突复核，输入契约升级rescan-v2。重载实际Worker后新建一轮重扫；inline方式则重载8100。无需新迁移/依赖/8000或前端改动，既有错行不会自动回滚/删除，候选仍需确认，真实终点质量尚需复测。见[排障](../../docs/service/agent/changelog/2026-10-19-rescan-identity-evidence.md)。

Explain普通自动解释现在限定当前会话重扫事实，并通过allow_rescan=false隐藏/拒绝提取工具；用户主动输入或重扫按钮仍可调用，项目历史仅主动查看。需重载8100及8000 API2.9.0并刷新Web，Worker不因本轮改动调整，无新迁移。见[边界记录](../../docs/service/agent/changelog/2026-10-18-explain-request-modes.md)。

若Explain出现`stream_error=true`，表示供应方在已建立的HTTP200流中返回错误。006M01已复现当前模型发布检查点不可加载，需供应方恢复或配置可用模型；重载8100只加载正确错误提示，不能修复供应方模型资源。见[根因记录](../../docs/service/agent/changelog/2026-10-18-explain-errors.md)。

Explain排障：流式接口的HTTP200只表示连接建立，实际失败通过SSE error事件传递。重载8100后，前端会区分模型HTTP状态/格式错误与数据服务异常，终端打印`Explain request failed ... code=... upstream_status=...`，不打印密钥或模型原始响应。无需改启动命令、数据库或Worker配置。见[诊断记录](../../docs/service/agent/changelog/2026-10-18-explain-errors.md)。

2026-10-18 Explain新增`rescan_connections`：按原Profile复用提取核心，原页/关联图加上传细节生成候选，用户确认后才更新线表。迁移`20261018050000`需先部署；加载8000 API2.8.0、8100及下方独立Worker的新代码。Worker启动指令不变，同一进程同时消费正常提取和重扫，不需要新增端口或再开一个重扫服务。使用独立Worker时保持`AGENT_INLINE_WORKER=false`；开发时可选择inline方式，二选一。见[交付](../../docs/service/agent/changelog/2026-10-18-explain-rescan.md)。

2026-10-18按用户要求，整份PDF遍历正常结束即处理完成，单页错误只留诊断，不再提交EXTRACTION_PARTIAL失败；真正中断仍失败。刷新前端可兼容已跑完的旧部分失败项目，后续执行由用户重启实际提取Worker加载新代码，无需数据库/API迁移。见[说明](../../docs/service/agent/changelog/2026-10-18-extraction-finished-status.md)。

2026-10-18提取初扫单页失败改为记录并继续后续页，全部遍历后若仍有错误则汇总未完成项，保留重试入口。重启实际提取Worker后，可在原失败项目点击“重试提取”，保持原模型/冻结规则/配置即可复用成功页，不必重新上传。配置/存储/租约/取消仍立即中止。本轮未重启服务或重跑模型，见[说明](../../docs/service/agent/changelog/2026-10-18-extraction-page-failure.md)。

2026-10-18 Explain新增`propose_connection_edit`：模型只生成持久修改对照，用户确认由8000事务提交。复用8100宿主，无新增端口/环境变量；本项目本地已应用`20261018020000_explain_connection_edits.sql`，加载8000/8100新代码即可，其他环境需先迁移，提取Worker不用调整。见[Explain说明](./src/agent/explain_agent/README.md)。本轮不运行真实模型或改真实线表。

2026-10-18 Profile现有规则编辑已接通Extraction的查看规则界面：可信Storage/本地包派生草稿、手动修改及工具聊天诊断/建议、用户确认后发布替换新版。沿用下方8100启动命令，需用户重新加载8100及8000 API2.6.0；本地新迁移已部署，未代发规则或启停服务。见[交付](../../docs/service/agent/changelog/2026-10-18-profile-resource-editing.md)。

2026-10-17修复Profile同页纠正后循环确认：新增受控返回初扫的内部动作，复用原图生成待确认修正候选。由用户重载8100，使代码和Prompt同时加载，无需新端口/迁移或重做分类。见[修复记录](../../docs/service/agent/changelog/2026-10-17-profile-repeated-clarification.md)。

Profile模型失败现在会在8100终端输出分类日志，前端显示错误码和诊断编号，私有响应保存在`.runtime/profile-agent/model-traces`。完整说明见[诊断记录](../../docs/service/agent/changelog/2026-10-17-profile-model-errors.md)。由用户重载8100生效；SSE HTTP200仅表示连接建立，请同时检查error事件。本轮未运行实际模型或操作用户服务。

2026-10-17 Profile新增[内存PDF抽样工具](../../docs/service/agent/changelog/2026-10-17-profile-pdf-sampling.md)：第一阶段随机选两页后只渲染选中页，保留草稿样图和来源元数据；原PDF及其余页不落盘。第二/三阶段通过附件来源标记限制为用户上传图片。沿用8100共享宿主，重载当前代码即可；无需新依赖/配置，原图片入口兼容。

2026-10-17 Profile新增[引导式规则对话](../../docs/service/agent/changelog/2026-10-17-profile-conversation.md)：LangGraph根据文字/样图追问或生成候选，逐阶段明确确认，复用原草稿与发布边界。沿用8100共享宿主，重新加载`src.extraction_main`即可提供新对话路由，无新增端口/环境变量。只有用户发送对话或样图时才调用模型，默认测试为Fake；本轮未运行真实模型或重启用户服务。

2026-10-17 Profile三步创建向导已挂载共享`src.extraction_main`的8100服务，无新增端口。配置沿用当前模型及内部令牌；草稿保存于`.runtime/profile-agent`。用户点击“根据图片生成规则与答案”才调用VLM。使用步骤及部署前置见[模块说明](./src/agent/profile_agent/README.md)。独立提取Worker也需加载新代码才能读取已发布的Storage规则包。

2026-10-17新增独立[Profile Agent](./src/agent/profile_agent/README.md)：根据样例/描述填充模板、基于证据诊断、确认建议或明确指令后编辑草稿、确认Expected并输出校验包。独立CLI/SDK无需另开HTTP端口；规则页与正式发布后接，不修改Explain或原始Profile。当前共享宿主未注册本模块路由。

2026-10-17 Explain来源浮窗已接入8000鉴权代理与共享8100宿主，支持行/页自动解释、流式工具记录及图纸。使用下方src.extraction_main入口即可同时提供Explain API；不需要每个Agent单独端口。旧src.main未挂本功能，需在自己的终端加载新入口。完整[交付](../../docs/service/agent/changelog/2026-10-17-explain-host.md)。

如果已单独启动提取Worker，可只启动HTTP宿主，不重复启动Worker：

```powershell
$env:AGENT_INLINE_WORKER = "false"
.\.venv\Scripts\python.exe -m uvicorn src.extraction_main:app --app-dir services/agent --host 127.0.0.1 --port 8100
```

沿用services/agent/.env的数据库和模型配置。Server的SERVER_AGENT_URL默认http://127.0.0.1:8100；Server和Agent的AGENT_INTERNAL_TOKEN应一致，生产AGENT_ENV=production必须配置令牌。Worker本身没有HTTP端口，提供Explain时仍需上述共享宿主。未自动重启现有服务或调用真实模型。

启动排障：终端持续显示claim_simple_extraction返回200，只能证明提取Worker正常；来源解释需要另有8100 HTTP服务。若前端提示Agent未启动，请检查http://127.0.0.1:8100/health；已单独启动Worker时，使用上面的inline=false命令补启动HTTP。2026-10-17本地已按此补启动，后台PID/日志位于.runtime/explain-http，用户现有Worker保持运行。

2026-10-16 [Explain Agent](src/agent/explain_agent/README.md)已扩展为模型可调用只读工具：按来源/目标页、原理号和起终点端子精确查询，返回线表及关联图纸，支持分页覆盖和按需看图。LangGraph条件循环、查询/图像摘要刷新、HTTP/SSE与CLI契约同步；51项Explain/共94项相关离线回归、Ruff/类型检查通过。未挂8000/8100或前端、未运行真实模型/数据库或写库。见[交付](../../docs/service/agent/changelog/2026-10-16-explain-retrieval.md)。

2026-10-16新增独立[Explain Agent](src/agent/explain_agent/README.md)：LangGraph按所有者权限只读当前行、原页/跨页和已保存提取证据，支持文字追问、字段差异提示及公开回答流。提供Python/CLI和由宿主注入鉴权的可挂载router，尚未挂到8000/8100或接前端，不新增服务/端口。20项模块、连同共享网关/Server共59项离线回归及Ruff/类型检查通过，未运行真实模型或写库；见[记录](../../docs/service/agent/changelog/2026-10-16-explain-agent.md)。

2026-10-16新增三表增量提取Worker：上传由8000 API入队，图片/分类/初扫/每组补全/页完成分别发布。review由程序计算，模型只报告事实与不确定性。新入口独立于旧Supervisor；旧`src.main`不消费此队列。详见[交付](../../docs/service/agent/changelog/2026-10-16-incremental-extraction.md)。随后启动排障已将20261016020000部署到本地zhenghua_test库，四个RPC可见；未启动付费提取。

## 当前增量提取的启动方式

本地zhenghua_test已应用`20261016020000`，8000 API已核对为2.1.0，无需重复执行迁移。新环境仍需先按Server说明应用`supabase/migrations/20261016020000_incremental_extraction.sql`并重载8000 API。配置`services/agent/.env`中的`AGENT_SUPABASE_URL`、`AGENT_SUPABASE_SERVICE_ROLE_KEY`、`AGENT_MODEL_BASE_URL`（或完整chat completions地址）、`AGENT_MODEL_API_KEY`和`AGENT_DEFAULT_MODEL`。使用本地Profile目录，不要求远端Profile控制面。

如果出现`claim_simple_extraction`的HTTP 404，先核对该数据库是否应用上述迁移及PostgREST是否重载Schema；这不是模型权限错误。

从仓库根目录运行独立Worker（推荐，无HTTP端口）：

```powershell
.\.venv\Scripts\python.exe -m pip install -e services/agent
Set-Location services/agent
..\..\.venv\Scripts\python.exe -m src.agent.extraction_agent.application.incremental_worker
```

或从仓库根目录运行带探活的开发主机（二选一）：

```powershell
$env:AGENT_INLINE_WORKER = "true"
.\.venv\Scripts\python.exe -m uvicorn src.extraction_main:app --app-dir services/agent --host 127.0.0.1 --port 8100
```

`GET http://127.0.0.1:8100/health`的`worker_running`反映inline Worker状态。前端仍只请求8000。真实上传会触发已配置模型调用；本地CLI的`--allow-real-model`保护仍保留，测试默认使用Fake模型。任务产物位于被忽略的`.runtime/incremental-extraction/<run_id>`。失败后在工作台点“重试提取”，成功模型响应和完成页复用；恢复需要原模型/图片配置，冻结Profile从私有Storage读取。

2026-10-18上传与脚本统一为`stage2-script-aligned-v1`。更新代码后须重启实际执行提取的Worker，启动日志核对`contract=stage2-script-aligned-v1`；然后新上传并选择zh_crop 2.2.1验证。旧任务配置不包含该契约，不能混用新请求与旧成功页缓存。前端/API无需因本次更新重新构建，具体核对见[交付](../../docs/service/agent/changelog/2026-10-18-extraction-entry-alignment.md)。

以下较早Supervisor/旧表/规则发布内容为历史运行说明，当前增量链路使用上面的入口。

2026-10-14目录迁移：独立提取实现位于[src/agent/extraction_agent](./src/agent/extraction_agent/README.md)，共享服务包按当前目录改为src，API入口为src.main:app。算法、Prompt和expected不改，只调整引用；静态比对完成，未运行模型/业务测试。现有测试脚本参数不变，见[迁移记录](../../docs/service/agent/changelog/2026-10-14-extraction-agent-directory.md)。

2026-10-14本地ZH2.0.2按用户新口径精简规则，读取放线段两侧直接端子，业务端子排仅后处理映射，保留电流约束。用户自行测试，本轮未运行测试/模型，不写数据库或发布；见[记录](../../docs/service/agent/changelog/2026-10-14-zh-direct-terminals.md)。

2026-10-13 Supervisor 对话微调：专业电气图纸与线表助手增加 CHAT 路线，日常交流流式输出公开回答、不分派工作流；真实 PDF 才能进入类型确认及 Stage 1/2 提取。任务说明后展示卡片，保留纠错/规则修改确认和权限检查。SSE 只发送 `delta.content`，不发送模型内部推理；运行服务需加载新代码。见[对话交付](../../docs/service/agent/changelog/2026-10-13-supervisor-chat.md)。

2026-10-13 本地ZH2.0.1：方向缺失降级、原始引用解析、分支保留与端子身份校验；40项冒烟及7项接口/兼容回归通过。旧结果保留，尚未重跑真实模型，数据库与远端规则未变。见[变更记录](../../docs/service/agent/changelog/2026-10-13-zh-stage2-quality.md)。

本地测试入口：已有拆页/索引用`scripts/run_stage2_groups.py`，导出标准12列加两端坐标共14列，色标留空；新PDF用`scripts/run_page_workflow_extraction.py`自动拆页/分类/提取并输出含诊断列的table.xlsx。两者支持`--profile zh|abb|zh_gantry_reel`和`--model`，强制内存/本地资源，不写数据库/Storage；真实模型须`--allow-real-model`。命令和产物见[测试说明](../../docs/service/agent/local-stage2-group-test.md)。

2026-10-13 分支更新：提取改为 Stage 1 分类 + Stage 2 独立逐页 LangGraph，扫描/双图补全/保存形成闭环，删除独立 Stage 3 Agent 和全局补全阶段。实现见 [ADR-0014](../../docs/adr/0014-stage2-page-extraction-workflow.md) 与 [交付记录](../../docs/service/agent/changelog/2026-10-13-stage2-page-workflow.md)。本轮仅离线冒烟，不写真实数据库、不发布远端包、不重启服务；旧持久 run 只读，新 run 使用冻结 `page_extraction_v2` 工作流，真实库运行前需要未部署的新 migration。以下早期实施状态作为历史上下文。


规则库支持人工基于可用模板创建新 key，封存到私有 Bucket 后立即注册；所有登录用户共享读取，创建者确认删除后停用。要求 `AGENT_PROFILE_PACKAGES_ENABLED=true` 和既有 Supabase 配置。Profile API/新任务入口/首页检测刷新远端 active 集合并为同 key 选择最新版本；已冻结任务仍使用原 checksum。首次使用新增 adapter 需重载服务以加载新代码。见 [ADR-0012](../../docs/adr/0012-shared-ready-rule-library.md)。

2026-10-13 起，规则修改取消评测/二次审核：[ADR-0013](../../docs/adr/0013-confirmed-rule-update-without-evaluation.md)。聊天归因建议经一次“确认规则修改”后直接构建并启用包。已有候选由 `run_rule_release.py --candidate-id ... --user-id ...` 接续，输入“确认规则修改”即可；不调用模型评测，不需要 `AGENT_ALLOW_REAL_EVALUATION` 或脚本真实模型开关。需应用 migration `20261013000000` 并重载 API/Worker（不自动停止现有任务）。详见 [`纠错验收说明`](./agent_test/2.纠错agent/README.md)。

局部纠错现按用户要求改为原位更新（[ADR-0010](../../docs/adr/0010-in-place-confirmed-corrections.md)）：直接答案和 Stage 2/3 重识别在确认后保持连接 ID/线号不变，使用 revision/record_version 校验并保留 feedback 审计。完整提取仍产生代次。`20261011020000` 已在本地部署；现有服务需由用户重载才使用新提交代码，旧历史没有删除。见[实施记录](../../docs/service/agent/changelog/2026-10-11-in-place-corrections.md)。

纠错混合批次和 Profile 资源包的实现说明见[实施记录](../../docs/service/agent/changelog/2026-10-11-correction-packages-implementation.md)，本地 migration/ZH bootstrap 已部署，见[部署记录](../../docs/service/agent/changelog/2026-10-11-profile-package-deployment.md)。API/Worker 加载新代码前需要设置 `AGENT_PROFILE_PACKAGES_ENABLED=true`；现有服务未重启。本地 Profile 默认兼容模式不受影响。验收复用 test0；已有候选通过上述终端入口接续，不重复注错或执行纠错。

独立的 Python Agent API、运行底座和图纸 Profile 服务。默认监听 `8100`，不创建用户或直接覆盖生产线表。迁移期内部验收可登记已有 owner 的项目/源 PDF，并通过受控事务创建结果版本；不替代业务 Server 的浏览器鉴权入口。

当前已实现 Agent 服务骨架、Profile Router、ZH 三阶段本地提取链路，以及 Run/Worker、Supervisor、Correction 和 Improvement 的受控执行基座：

阶段 0 的纯 HTTP 终端验收见 [`agent_test/0.detection_test/README.md`](./agent_test/0.detection_test/README.md)。Supervisor 现具备进程内短期会话记忆，支持上传会话 PDF、只识别类型、等待用户确认，以及确认后追问当前类型；长期记忆和跨进程对话恢复尚未实现。

Gate A 的正式 Supabase FULL_EXTRACTION 使用 protocol 2：各阶段提交后从数据库重新加载，上游项/输入固定，支持过期 RUNNING 接管、fencing、空缓存恢复和结果 receipt 驱动的幂等收尾。旧 run/旧脚本保留 protocol 1；本地三阶段 CLI 仍不落库。实际验证与命令见 [Gate A 记录](../../docs/service/agent/changelog/2026-10-10-gate-a-implementation.md)。

Gate B 内部上传/确认/Worker/SSE 链路已接通，见 [阶段 1 HTTP 验收说明](./agent_test/1.3stage/README.md)。`/v1/imports` 要求已有 Supabase Auth 用户 UUID、内部 Bearer 和 Idempotency-Key；确认后原子登记带冻结 Profile 的持久 run。项目树只读 published snapshot，结果按固定版本分页，SSE 支持 Last-Event-ID。真实模型字段准确率和 Web/JWT 代理尚未验收。本地已应用 `20261011000000` 原子入队 migration，部署其他库时须应用新增 migration。

- FastAPI 应用、配置、日志和健康检查；
- Run/Event/Proposal/Correction/Supervisor 公共领域契约；
- Model Gateway、Tool Registry、Context、Checkpoint 和 Trace 最小 Harness；
- Profile Registry、版本化 ZH Profile 和动态资源绑定；
- 只读取 PDF 物理首页的 Profile Router、人工确认和动态 ProfileBinding。
- Stage 1 `PageClassifierAgent` 与 Stage 2 页工作流；`PageScannerAgent` 提供初扫及内部补全操作，保持 Pydantic 契约；
- ZH `ZhVlmExtractionStageAdapter` 通过 Agent 自己的 OpenAI-compatible Model Gateway 调用模型，分类、初扫和内部补全都发送真实图片 Few-shot；
- 文档 Graph 位于 `graphs/document_extraction`；PDF/checkpoint/JSON/XLS(X) 位于 `infrastructure/document`；端子、方向、电流、引用解析和导出字段通过 `profiles/zh` 策略注入；`zh_workflow` 兼容目录已删除；
- `scripts/run_page_workflow_extraction.py` 执行分类及逐页闭环提取，输出两阶段 JSON、完成页 checkpoint 和 XLSX，不写数据库；
- Supervisor 意图 Graph、Workflow Registry、首页 Profile Detection 内部工具，以及按项目/工作区/业务页码/线号/端子检索的受控结果工具；
- 三态 `is_cross_page` 纠错路由、Correction proposal、用户确认后的 Supabase 原子版本提交和 accepted-feedback Improvement 触发；
- Improvement Diagnoser 的脱敏原因/建议事件、显式授权后的 Profile Patch Builder、Evaluation Judge、离线 Eval Runner、Profile Sandbox 与确定性 Release Gate。

M4 的真实 VLM 首页识别评测和 ZH 固定案例字段级回归仍未执行。Agent HTTP 服务提供健康检查、Profile、Run 控制、事件查询/SSE、Proposal 查询、Supervisor 回合及候选审核路由。默认 `memory` 模式用于离线测试；设置 `AGENT_PERSISTENCE_BACKEND=supabase` 与 `AGENT_CHECKPOINT_BACKEND=supabase` 后，Run/Event/Artifact/Proposal/Checkpoint、源 PDF 和任务队列持久化到 Supabase，队列通过数据库租约支持独立 Worker 跨进程消费。`AGENT_INLINE_WORKER=true` 仅用于同进程开发。HTTP Run 只接受已登记的 source-document 对象引用，不接受任意本地路径。

Supabase 模式下，完整提取 Proposal 会原子写入规范化结果版本；source document 和 Correction drawing 会从私有 Bucket 下载并校验或重新物化。受控结果工具支持多条件查询、持久 Correction bundle、乐观版本提交和 accepted feedback；Profile candidate、release gate、eval、状态审计和模型 Trace 也会持久化。Stage 1/2/3 本身仍只返回结构化候选，只有完整提取持久步骤或用户明确确认修订后才调用受控提交 RPC。

ABB Profile 1.1.2 使用独立三阶段 Prompt，各阶段仅一案例：Stage 1 原页 205、Stage 2 原页 205（示范 Q4 跨页连接）、Stage 3 原页 205+目标页 241。资源已上传私有 `agent-profile-assets` 并读回校验；`abb_native` VLM adapter、Sheet/Cont 页面索引、跨页引用与确定性策略已注册，全量 Graph 可执行。真实模型字段级质量仍待人工验收。见 [ABB 资源说明](src/agent/extraction_agent/prompts/abb/README.md)。

上传可用规则资源包（不覆盖不可变旧包；使用已有 Auth 用户 UUID）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/upload_profile_package.py abb `
  --user-id "<已有 Auth 用户 UUID>"
```

脚本上传后下载全部资源并校验 checksum；三阶段 schema、manifest 和路径会在打包时校验。样例图片副本可通过 `services/agent/scripts/prepare_abb_example_images.py` 复现。

## 启动

以下命令使用 Windows PowerShell，从仓库根目录执行；克隆路径不同时调整 `Set-Location`。需要 Python 3.10+。完整本地联调按 Agent（8100）→ [Server/API（8000）](../server/README.md#启动) → [Web（5174）](../../apps/web/README.md#启动) 的顺序，在独立终端启动。

首次准备虚拟环境、Agent 包及其运行/开发依赖，已有环境和配置时保留：

```powershell
Set-Location E:\project\zhenghua_test
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e "services/agent[dev]"
if (-not (Test-Path services\agent\.env)) { Copy-Item services\agent\.env.example services\agent\.env }
```

编辑 `services/agent/.env`，填写模型地址、`AGENT_MODEL_API_KEY` 和 `AGENT_DEFAULT_MODEL`，确认 `AGENT_INTERNAL_TOKEN` 与 Server 一致。`AGENT_MODEL_BASE_URL` 填服务根地址（通常以 `/v1` 结尾），也可以直接填写完整的 Chat Completions 地址到 `AGENT_MODEL_CHAT_COMPLETIONS_URL`。

Agent 只读取 `services/agent/.env`，不会加载仓库根目录或 `backend/.env`。运行进程中显式设置的环境变量优先；模型配置兼容旧 `VLM_*`，Supabase 凭据兼容旧 `SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY`。旧 `SUPABASE_STORAGE_BUCKET=images` 不会被继承，Agent 新链路默认使用私有 `project-assets`。`AGENT_INLINE_WORKER` 只适用于同进程开发测试。

生产持久模式至少需要：

```dotenv
AGENT_PERSISTENCE_BACKEND=supabase
AGENT_CHECKPOINT_BACKEND=supabase
AGENT_SUPABASE_URL=http://127.0.0.1:54321
AGENT_SUPABASE_SERVICE_ROLE_KEY=...
AGENT_SUPABASE_STORAGE_BUCKET=project-assets
```

不要沿用旧公开 `images` Bucket。新链路的原始 PDF、页面图片和阶段产物必须写入 migration 创建的私有 `project-assets`；service-role key 只允许存在于 Server/Agent 进程环境中。

启动 Agent API 和本地同进程 Worker：

```powershell
Set-Location E:\project\zhenghua_test
$env:AGENT_INLINE_WORKER="true"
.\.venv\Scripts\python.exe -m uvicorn src.main:app `
  --app-dir services/agent `
  --host 127.0.0.1 `
  --port 8100
```

`AGENT_INLINE_WORKER` 默认是 `false`；上面的进程环境变量开启本地开发 Worker，否则只启动 HTTP API，排队任务需要其他 Worker 消费。使用 `memory` 队列时 API 与 Worker 必须在同一进程；真实工作台上传和持久提取需要上面的 Supabase 配置、已应用的所需 migration 和可用私有 Bucket。该开发命令沿用 `.env` 中的持久化配置，不会将 Supabase 模式切换为内存模式。仅本地图纸、不落库的测试请使用下方独立 CLI 或[分组测试说明](../../docs/service/agent/local-stage2-group-test.md)。

接口文档为 `http://127.0.0.1:8100/docs`。启动后可在另一终端检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health/live
Invoke-RestMethod http://127.0.0.1:8100/health/ready
```

停止当前开发服务使用 `Ctrl+C`。处理任务期间避免启用自动 reload，以免中断模型调用及进程内会话。

未配置模型时，`/health/live` 仍返回 `200`，`/health/ready` 返回 `503` 并列出未就绪项。

```text
GET http://127.0.0.1:8100/health/live
GET http://127.0.0.1:8100/health/ready
GET http://127.0.0.1:8100/v1/profiles
GET http://127.0.0.1:8100/v1/profiles/zh/versions/1.0.0/rules
POST http://127.0.0.1:8100/v1/runs
GET  http://127.0.0.1:8100/v1/runs/{agent_run_id}/events/stream
POST http://127.0.0.1:8100/v1/supervisor/turns
```

## 测试

默认测试不调用真实 VLM：

```powershell
$env:PYTHONPATH="services/agent;."
.\.venv\Scripts\python.exe -m pytest services\agent\tests
```

本地 Supabase 启动并应用 migration 后，可运行真实持久化冒烟。脚本会创建临时用户和项目，验证完成后清理，不调用 VLM：

```powershell
$env:PYTHONPATH="services/agent"
$env:AGENT_SUPABASE_URL="http://127.0.0.1:54321"
$env:AGENT_SUPABASE_SERVICE_ROLE_KEY="..."
$env:AGENT_SUPABASE_ANON_KEY="..."
$env:AGENT_SUPABASE_STORAGE_BUCKET="project-assets"
.\.venv\Scripts\python.exe services\agent\scripts\verify_supabase_production_foundation.py
```

该冒烟覆盖私有 Storage、签名 URL、RLS、PDF checksum、页面发布、租约队列、并发事件序号、Artifact、Proposal、Checkpoint 乐观锁与从 1000 开始的并发线号分配。

完整数据库工作流验证不调用 VLM，覆盖提取落库、结果查询、纠错确认、新版本、accepted feedback、Trace、候选、评测、门禁和审计：

```powershell
$env:PYTHONPATH="services/agent"
.\.venv\Scripts\python.exe services\agent\scripts\verify_supabase_agent_database_workflows.py
```

若当前环境没有安装可选开发依赖 `pytest`，可用 `unittest` 执行迁移相关回归：

```powershell
$env:PYTHONPATH="services/agent;."
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_agent_settings.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_atomic_checkpoint.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\unit -p "test_native_vlm_stages.py"
.\.venv\Scripts\python.exe -m unittest discover -s services\agent\tests\integration -p "test_standalone_three_stage_workflow.py"
```

## 三阶段提取

所有模板主表统一为14列：页码、原理号、端子排、起点元件、起点描述、起点端子、终点元件、终点描述、终点端子、电流、色标（空）、备注、起点端子坐标、终点端子坐标。公共Graph、本地PDF/拆页入口及原生XLSX共用domain/table_output.py，默认样式沿用ZH基线，固定下游业务导入模板另保留自身格式。元件取device优先、位置为回退；描述不混入part，备注不自动混入source_note，实际端子值不在某个入口额外加设备前缀。

ABB1.1.4、XMZ（zh_gantry_reel）0.1.2与ZH一样要求实际端子坐标：整张图左上为原点的0到1归一化x/y，以及该端所在图片PDF物理页号；补全目标来自目标图，起点坐标冻结。原图等比例缩放不改变坐标系，未知端子/无法定位时null。样例按图片目视标注近似位置，真实坐标精度待复测。旧结果不被覆盖，缺失坐标不能自动补回；新Profile版本应使用新输出目录，避免旧完成页指纹冲突。

所有模板均接收共享Pydantic JSON Schema；`enforce_evidence_contract`仅控制ZH专属语义说明/校验，不再让ABB漏掉输出契约。服务商`response_format`仍由`AGENT_MODEL_JSON_MODE`显式控制，不自动打开。JSON语法重试包含错误位置；明确`finish_reason=length`且JSON不完整时停止并报告长度限制，不静默修补或截取部分结果。

本地`run_page_workflow_extraction.py`在输出目录`model_calls/`保存每次模型原始响应、`finish_reason`、token用量及阶段/图片尺寸metadata，格式失败的返回也保留。日志为传输层结果，不表示内部提取JSON已校验通过；不保存请求消息、认证或图片base64，不写数据库。服务端未提供停止原因时为null，不能仅凭报错字符位置认定截断。旧失败运行没有保存的原始响应无法补回；需要用户重新运行，诊断文件不提交仓库。

Stage 2/3 会保留 manifest 中的图像 Few-shot，但发送给模型前会将最长边超过 `AGENT_MODEL_FEWSHOT_MAX_IMAGE_SIDE` 的样例图按 2 的幂次缩小，默认最长边不超过 1800 像素。磁盘中的案例图片和待提取原图不变；该配置只控制 Few-shot 请求图像大小。

2026-10-15图片预算改为实际输入优先：分类、初扫和双图补全先保留`AGENT_MODEL_INPUT_MAX_IMAGE_SIDE=2048`上限内的实际图，Few-shot分享`AGENT_MODEL_MAX_TOTAL_IMAGE_PIXELS=6000000`总预算的剩余部分。先压缩案例；其最长边缩到`AGENT_MODEL_FEWSHOT_MIN_IMAGE_SIDE=768`下限仍放不下时，从末尾整组移除案例图/任务与expected，保留现有manifest靠前顺序，不拆散双图或留下孤立答案。只有去掉所有案例后实际图自身仍超预算，才进一步缩小实际图。原图不放大/裁剪/改写，归一化坐标不变。

metadata与本地日志记录`vision_budget_policy=input_first_v1`、实际发送尺寸、案例保留/删除数量和索引、实际图是否额外缩小；策略/配置进入完成页指纹。分组CLI默认`--completion-max-side 0`，由统一预算层处理实际图，显式设置该参数仍可额外预缩放。原图更小则不放大，当前2048px和600万像素上限未自动提高，像素预算仍不等于供应商私有patch公式。修改无需重新拆页，复测使用新输出目录；本轮未运行测试/真实模型。详见[设计/交付](../../docs/service/agent/model-image-budget-plan.md)。

Stage 2 的完整入口为 `graphs/document_extraction/page_extraction.py` 中的 `run_page_extraction`，可包装为主 Agent 的工具/子 Agent；初扫模型节点 `run_page_scan` 不是完整提取入口。文档级入口为 `application/page_workflow_extraction.py::run_page_workflow_extraction`。

流程：分类全部页并建立索引 → 本页初扫起点 → 内部引用规划 → 来源图/唯一目标图定向补全 → 校验 → 保存完成页 → 下一页。不扫描目标页其他连接，不递归扩张引用。跨页无法确认时终点 null、needs_review；配置/权限/持久化失败仍停止，不把写入失败当作完成。

ZH 2.0.0 取消 XA/XD 白名单与强制换向，按实际放线标记/路径和箭头判断来源；无箭头保留模型证据，方向不确定待复核。实际端子标识保留，端子排明确值优先，否则按已知端子映射，无法映射留空。PE 不自动填颜色/未确认终点，业务代号不凭常识转换。新样例有 C01 正例、C03 接收端局部负例、C01→C02 双图补全；旧白名单 expected 归档为 legacy，真实模型与人工基线验收尚未完成。

本地完成页存于 `agent/completed-pages/<physical-page>.json`，输入/Profile/图片指纹变化会拒绝旧缓存；恢复跳过完成页。数据库模式初扫/补全模型缓存与完成页 StageItem 分离，最终业务版本仍通过 Server 原子提交。`supabase/migrations/20261013010000_stage2_page_workflow.sql` 只新增冻结工作流前驱/完成页事实校验，未执行；没有修改已应用迁移。已有旧 run 不续跑混合阶段，应新建 run；既有项目不重绑 Profile。

离线冒烟（禁止网络请求，不调用模型/数据库）：

```powershell
.\.venv\Scripts\python.exe -m pytest services/agent/tests/smoke/test_stage2_page_workflow.py -q
```

真实模型 CLI 需要显式授权开关，以下命令不属于本轮验证：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_page_workflow_extraction.py `
  "case/example.pdf" --output-dir "runs/page-extraction" --allow-real-model
```

`01_page_classification` 保存分类/索引，`02_page_scan` 保存扫描/内部补全/最终表格，最终预览为 `02_page_scan/table.xlsx` 和根目录 `table.xlsx`，不再创建 `03_cross_page_completion`。历史阶段枚举、CorrectionAction、`cross_page_prompt` / `stage3_cases` 资源标识保留用于读取旧数据，不代表新运行有独立 Stage 3。ABB Prompt 未调整，内部操作保持其原单目标查询图片契约。

## M4 Profile 首页识别

M4 只读取 PDF 物理首页。默认测试使用 Fake VLM；真实模型识别必须显式执行：

```powershell
$env:AGENT_MODEL_BASE_URL="http://your-model-host/v1"
$env:AGENT_MODEL_API_KEY="..."
$env:AGENT_DEFAULT_MODEL="your-vlm"

.\.venv\Scripts\python.exe services\agent\scripts\test_profile_detection.py `
  "case\1002001641 PERU TPP 1 STS.pdf"
```

无法自动识别或识别到 experimental Profile 时，结果为 `WAITING_INPUT`。可在测试中模拟用户确认：

```powershell
.\.venv\Scripts\python.exe services\agent\scripts\test_profile_detection.py `
  "case\abb\ABB原理图说明.pdf" `
  --confirm-profile abb
```

确认结果生成不可变 `ProfileBinding`，其中包含 Profile 版本、checksum、公开规则和三阶段动态资源映射。

## 边界

- `src.domain` 不依赖 FastAPI、数据库 SDK 或模型供应商。
- 新原生子 Agent 通过 Harness 调用模型与工具；`legacy_zh_adapter.py` 与 `legacy_zh_stages.py` 仅保留旧 Agent 调用方的兼容入口，不导入或执行旧 `backend` 实现。
- `LegacyZhExtractionAdapter` 只返回候选结果，不提交生产数据。
- `LegacyZhStageAdapter` 只执行单阶段 VLM 调用并返回候选 Schema，不负责索引、最终校验或生产数据写入。
- ABB 当前可作为新任务 Profile；真实模型准确率基线仍未完成，验收前应保留人工确认和 `needs_review` 路径。
- Supabase 模式已持久化 Run/Event/Artifact/Proposal/Checkpoint/Trace、源 PDF、页面图片、规范化结果版本、Correction/accepted feedback、候选、评测、门禁审计和租约队列。启用远端资源包后，候选评测从冻结 Bucket 包读取，人工审核/发布通过服务端 receipt；隔离沙箱不直接覆盖生产 Profile。Bucket 发布执行器已实现，真实模型评测和发布验收待执行。
