# Server 业务服务

2026-10-20一键审核使用review_extraction_scope原子事务及API2.16.0。限定迁移脚本新增 `--migration 20261020020000 --apply`，本地已安装且业务摘要不变；重载8000刷新Web，见[记录](../../docs/service/server/changelog/2026-10-20-bulk-review.md)。

API2.15.0新增版本化人工复核、当前批次待复核聚合和目录状态覆盖；20261020010000迁移已安装本地且业务摘要不变。其他本地实例可用限定脚本 `services/server/scripts/apply_explain_edits_migration.py --migration 20261020010000 --apply`，需重载8000并刷新Web，见[交付](../../docs/service/server/changelog/2026-10-20-connection-review.md)。

API2.14.0同步Explain重扫requirements（所需字段/起点集合/同页约束）生成DTO，历史缺省JSON保持可读；确认事务与权限沿用，无migration。先重载8000再加载8100/实际Worker，刷新Web并新建任务，见[契约](../../docs/apps/api/changelog/2026-10-20-rescan-requirements.md)。本轮未修改真实库。

API2.13.0增加主助手历史永久删除及附件GC：`DELETE /api/v1/assistant/conversations/{id}`返回204，保留正式结果与独立任务。新增20261019050000迁移本地已部署，8000已加载，刷新Web即可；其他实例的部署/回滚边界及测试命令见[交付](../../docs/service/server/changelog/2026-10-19-assistant-conversation-deletion.md)。

2026-10-19 API2.12.0新增终点重扫target_bindings，Agent→Server→OpenAPI/TS及主助手参数已同步，无新迁移。重载8000及Agent/Worker后新建任务，见[契约记录](../../docs/service/server/changelog/2026-10-19-rescan-target-contract.md)。

2026-10-19新增迁移20261019030000：授权项目可显式让新重扫固定项目当前规则，已有任务不改绑，资源GC检查重扫引用。本地已部署并为指定STS项目启用ZH2.3.0；使用需重载Worker，不需为SQL变化重启8000。部署命令见[交付](../../docs/service/server/changelog/2026-10-19-rescan-project-profile.md)。

2026-10-19新增主助手有界编号范围与显式多编号检索、指定记录候选范围校验、复合任务全部回执核对；zh_crop仅在编辑时跟随已确认正式zh继任，诊断/旧项目保持原冻结版本。无新迁移，需8000/8100同步重载，见[记录](../../docs/service/server/changelog/2026-10-19-main-assistant-progress.md)。

2026-10-19主助手答复在执行回执核验后发送：校验当前用户/会话/轮次及真实run，再输出数据库编号与状态。需8000/8100一起重载，无新迁移/契约生成变更，见[修复](../../docs/service/server/changelog/2026-10-19-main-assistant-receipt-guard.md)。

2026-10-19新增主助手会话、强类型业务工具和确认服务，8000 API2.11.0；迁移20261019020000本地已安装并刷新Schema缓存，原业务数据不变。重载8000/8100后可由全局浮窗使用，见[接口、迁移与验证](../../docs/service/server/changelog/2026-10-19-main-assistant.md)。

2026-10-19规则选择改为仅数据库上传包：/rule-library与历史/local兼容选项只展示有效Storage引用，登记接口只定位已有包，上传/新建不再绑定local://。ZH2.3.0、ABB1.3.1、XMZ0.2.1已发布到当前本地库；旧引用/项目保持。用户重载8000并刷新Web，无需迁移或新增Worker，见[交付](../../docs/service/server/changelog/2026-10-19-database-profile-catalog.md)。

API2.10.0支持确认后的范围替换：全量删旧写新、局部仅更新选中内容，读持久候选/能力检测后才能提交。新增`20261019010000_rescan_scope_replacement.sql`已在本地应用，业务三表摘要不变，未执行替换。重载8000/8100/实际Worker并刷新Web，新建重扫；其他环境按顺序应用迁移。见[交付](../../docs/service/server/changelog/2026-10-19-rescan-scope-replacement.md)。

其他本地实例按需安装该迁移：`.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261019010000 --apply`。脚本检查明确的本地容器标签、备份Schema并核对业务表摘要；不会提交任何替换。缺迁移时API拒绝全量确认，防止旧RPC追加结果。

API2.9.0新增鉴权项目全量导出`GET /api/v1/projects/{project_id}/export.xlsx`，13列区分电压等级/端子排；固定当前正式批次、并发版本/权限核对，私有内存下载。Explain新增向后兼容allow_rescan参数；重载8000/8100并刷新前端，无迁移或Worker变化。见[导出交付](../../docs/service/server/changelog/2026-10-18-project-export.md)和[ADR-0035](../../docs/adr/0035-project-xlsx-export.md)。

导出离线验证：开发依赖可通过`.\.venv\Scripts\python.exe -m pip install -e 'services/server[test]'`安装，再运行`.\.venv\Scripts\python.exe -m pytest services/server/tests/test_project_export.py -q`。openpyxl仅作独立读取验证，生产导出不依赖它；测试不访问真实数据库或模型。

2026-10-18 API2.8.0新增Explain重扫附件、任务/证据读取、取消与候选确认。正式线表只在用户确认后修改，版本冲突整批拒绝；已登记辅助文件纳入项目删除，行删除清除相关重扫副本。本项目本地已部署`20261018050000_explain_rescan.sql`且三表摘要不变，其他环境先按顺序应用迁移；再重载8000/8100及现有独立Worker，启动命令不变，无新端口/环境变量。见[交付](../../docs/service/server/changelog/2026-10-18-explain-rescan.md)。

从仓库根目录部署或核验当前本地项目的单个迁移（脚本会检查容器项目标签并先备份Schema，不执行重扫）：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261018050000 --apply
```

隔离SQL验证（不连接当前业务库）：`$env:EXPLAIN_RESCAN_SQL_TEST="1"`后执行`.\.venv\Scripts\python.exe -m pytest services/server/tests/test_explain_rescan_sql.py -q`。候选有效24小时；需重新生成时在解释框明确要求重扫。其他环境按迁移顺序部署。

2026-10-18 当前交换约定已纠正：记录所属页/工作区与关联图纸索引固定，只交换元件/描述/端子/坐标对象。`20261018040000_swap_endpoints_keep_origin.sql`已在本地部署，旧迁页方案提交返回409；前端亦停用。指定4行归属恢复006C01/006.C，已确认端点与坐标保留。其他环境按顺序应用迁移；本地核验命令为 `.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261018040000`。无需新端口，前端刷新、Agent重载8100。恢复脚本只用于用户明确授权的旧方案和精确范围，默认只读预览，不应自动修复其他项目。见[记录](../../docs/service/server/explain-swap-origin-correction.md)。

2026-10-18 已部署 `20261018030000_connection_delete_no_snapshot.sql`：后续删行移除业务行及其审计/旧请求副本和相关修改方案，仅保留无端点值的幂等回执。迁移不批量改写旧历史，部署前后三表摘要不变。根目录执行 `.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261018030000 --apply` 可在明确的本地项目应用或核验；其他环境按迁移顺序部署。API形状不变，前端刷新、Agent重载8100。见[排障与验证](../../docs/service/server/changelog/2026-10-18-explain-delete-relocation.md)。

2026-10-18 API2.7.0新增Explain线表修改方案及确认：Agent生成逐行对照，用户在浮窗确认后Server原子提交、版本保护并审计。[新增迁移](../../supabase/migrations/20261018020000_explain_connection_edits.sql)已在本项目本地部署且三表摘要不变，REST可见两个RPC；重载8000和8100即可，无新增端口或Worker参数。其他环境须先应用迁移。本轮未改真实线表。隔离SQL测试：`$env:EXPLAIN_EDIT_SQL_TEST="1"; .\.venv\Scripts\python.exe -m pytest services/server/tests/test_explain_edits_sql.py -q`，仅创建独立临时容器。见[交付](../../docs/service/server/changelog/2026-10-18-explain-edit-transactions.md)。

2026-10-18 API2.6.0新增现有规则编辑代理和新版替换：只有规则所有者可派生草稿，手动编辑/公开工具聊天/建议确认与发布共用8100；无引用旧ZIP进入可重试回收队列，项目/任务仍用的旧版保留。新增`20261018010000_profile_editing_replacement.sql`已在本地部署，其他环境须先应用；沿用下方启动指令重新加载8000及8100，提取Worker无新增启动参数。见[交付](../../docs/service/server/changelog/2026-10-18-profile-editing-replacement.md)。

2026-10-17本项目本地库已补齐`20261017010000`发布迁移，解决已上传包却提示“数据操作失败”；REST Schema与包摘要检查通过，原草稿直接重试手动发布即可。其他环境仍须先应用该迁移；缺接口提示代码需下次加载8000生效。见[排障记录](../../docs/service/server/changelog/2026-10-17-profile-publication-missing-migration.md)。

2026-10-17 API2.5.0新增[Profile PDF抽样代理](../../docs/service/server/changelog/2026-10-17-profile-pdf-sampling.md)，沿用8000→8100鉴权链路及启动方式。只向Agent发送上传PDF供内存抽样，未存业务库或Storage。原有发布迁移不变，本轮没有新迁移。

2026-10-17 API2.4.0新增[规则对话GET与SSE代理](../../docs/service/server/changelog/2026-10-17-profile-conversation.md)，经JWT和内部令牌访问共享8100。沿用下方启动指令，由用户重新加载8000/8100后使用；本轮无新增迁移，发布仍使用原发布迁移。契约生成顺序保持不变。

2026-10-17新增Profile三步创建与手动发布：`/api/v1/profile/drafts`经JWT后代理8100可信用户；发布由Server校验并上传不可变ZIP，再调用`publish_extraction_profile`登记规则。启用前在目标Supabase应用[新增迁移](../../supabase/migrations/20261017010000_profile_wizard_publication.sql)，随后重新加载8000、8100和提取Worker。首次交付未部署；本地后续部署状态见上方排障记录。原本地规则继续可用，`/rule-library/local`为兼容路径，现也返回已发布规则。

契约同步：依次执行`services/agent/scripts/export_profile_contract.py`、`apps/api/scripts/export_openapi.py`和下方已有的openapi-typescript命令。隔离SQL验证使用`$env:PROFILE_PUBLICATION_SQL_TEST="1"; .\.venv\Scripts\python.exe -m pytest services/server/tests/test_profile_publication_sql.py -q`；它创建无网络/无业务卷的临时PostgreSQL容器并清理，不应用业务库迁移。

2026-10-17新增Explain来源解释接口，API版本2.2.0。浏览器POST /api/v1/explain/turns/stream，经Supabase JWT及三表项目所有者校验后转发共享8100的/v1/explain/turns/stream。用户身份由Server注入X-Explain-User-Id，不信任正文/浏览器同名头。只读、不修改数据或新增迁移，旧Supervisor保持未开放。见[交付](../../docs/service/server/changelog/2026-10-17-explain-proxy.md)。

沿用下方8000启动命令加载新代码，并启动[8100共享Agent宿主](../agent/README.md)。SERVER_AGENT_URL默认http://127.0.0.1:8100，AGENT_INTERNAL_TOKEN需与Agent一致；这些配置仅留服务端。前端仍只请求8000。仅启动提取Worker不会提供Explain HTTP。

Explain公共契约生成顺序（无数据库/模型调用）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/export_explain_contract.py
.\.venv\Scripts\python.exe apps/api/scripts/export_openapi.py
.\apps\web\node_modules\.bin\openapi-typescript.CMD apps/api/openapi.json -o apps/web/src/apis/generated.ts
```

explain_contract.py是生成文件，来源是Explain Agent的models.py；Schema一致性测试防止双端契约漂移。

2026-10-16增量提取已接入代码：上传PDF保存后创建提取任务，工作台通过Server SSE刷新已提交的图纸索引和线表。AI聊天仍未开放。启用前需部署新增迁移并启动[独立提取Worker](../agent/README.md#当前增量提取的启动方式)，原数据管理API继续使用8000。见[交付及验证](../../docs/service/server/changelog/2026-10-16-incremental-extraction.md)。

## 启用增量提取

按时间顺序应用现有迁移及新增`supabase/migrations/20261016020000_incremental_extraction.sql`，不要重复执行已应用迁移。新增迁移先通过隔离临时库验证；随后因Worker启动404，已应用本地zhenghua_test库并登记历史。无需重复应用。它增加四个内部RPC、领取/活动任务唯一索引、私有ZIP上传能力并兼容旧guard/行CRUD函数，不创建新业务表。

重载8000 API后启动新Worker；前端不需要Agent内部令牌或service-role。上传失败不入队，Worker未启动时显示排队等待，处理期间线表只读。失败保留已保存结果，可从工作台重试。

本地SQL验收命令（创建并移除一次性测试库，不修改当前项目库）：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/verify_incremental_migration.py --allow-local-database-test
```

旧`verify_simple_management.py`描述仅保存文件的历史验收，不再用于验证上传自动提取；当前验收使用新增SQL脚本、API测试及Agent Fake VLM测试。下文此前“无需Agent/上传不提取”说明为历史状态。

当前为三表数据管理模式（2026-10-16）：项目、规则引用、私有PDF登记、JSON图纸目录/预览、批次线表分页及行级增改删。HTTP入口位于apps/api/src/main.py，应用逻辑位于src/wiring_server/simple_*和profile_references.py。

业务表：extraction_profiles、extraction_projects、extraction_connection_rows。Supabase Auth和暂留Agent表保持独立；旧业务表已删除。本轮不执行Agent提取，上传后只保存文件，AI入口明确未接入。

结果行保留可空start_terminal_coordinates/end_terminal_coordinates JSONB：{x,y,pdf_page_number}为每端独立的归一化位置及所属PDF物理页。20261016010000已在本地部署，API/前端类型同步；修改端子/页号会清理对应旧坐标。定位高亮后续实现，详见[坐标契约](../../docs/service/server/terminal-coordinate-contract.md)。

## 启动

从仓库根目录，在原有后端终端按Ctrl+C后重新启动以加载新路由：

```powershell
Set-Location E:\project\zhenghua_test
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

首次安装依赖时使用`.\.venv\Scripts\python.exe -m pip install -e services/server`，包含PyMuPDF。配置仅需SERVER_SUPABASE_URL、SERVER_SUPABASE_SERVICE_ROLE_KEY及可选SERVER_WEB_ORIGIN，放services/server/.env；本地可沿用services/agent/.env中的SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY。密钥始终留在后端。当前无需启动Agent，也不需要SERVER_DATABASE_URL；旧Agent/直连配置保留为后续接入用。

默认本地Supabase为127.0.0.1:54321，Web为5174。规则引用目录默认services/agent/src/agent/extraction_agent/profiles，路径安全检查限制在工作区内；本地规则不完整时从可选列表排除，不阻塞项目列表。

数据库需已有20261014000000/20261014010000及20261016000000迁移。当前zhenghua_test已部署，不要重复执行create function/table。其他环境通过新migration创建三表并安装行管理RPC；不恢复旧业务表。

## API

- `/api/v1/auth/*`：Supabase账号登录、刷新和退出，JWT与Cookie来源校验保留。
- `/api/v1/projects`及`/{id}`：所有者项目列表、详情、创建、重命名、确认删除；`/{id}/source`生成原PDF签名URL。
- `/{project}/connections`：batch_id、分页、工作区/图纸过滤、搜索；来源PDF物理页/row_order/id排序。
- `/api/v1/connections/{id}`：基于record_version和Idempotency-Key的本行编辑，目标图从`/{id}/target`读取。
- 项目connections的POST/DELETE：来源/目标页必须在项目JSON索引中；删除需确认和行版本。before/after及回执保留到项目JSON，不增加审计表。
- `/api/v1/rule-library`、`/local`、`/{id}`：登记/删除本地规则引用和查看Prompt/Few-shot，不修改规则文件，不再调用旧候选/发布表。
- `/api/v1/imports`：原始PDF请求体，需profile_key、project_name、filename和Idempotency-Key；返回extraction_started=false。
- `/api/v1/capabilities`：数据管理可用，extraction/supervisor为false。旧Supervisor入口明确503，其他旧任务接口不纳入当前契约。

项目删除先归档，再清理经边界检查的登记文件路径，最后删DB行；失败保留归档状态供刷新重试，不删除别的项目对象。上传失败可使用相同标识/内容重试，文件未保存成功不会标记source_saved。

## 验证与契约生成

```powershell
.\.venv\Scripts\python.exe -m pytest services/server/tests -q -p no:cacheprovider
.\.venv\Scripts\python.exe apps/api/scripts/export_openapi.py
.\apps\web\node_modules\.bin\openapi-typescript.CMD apps/api/openapi.json -o apps/web/src/apis/generated.ts
```

真实本地HTTP/Storage验收会创建并清理一次性账号、项目和文件，须显式执行：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/verify_simple_management.py --allow-local-write
```

该验收限定127.0.0.1:54321，不调用Agent或模型。旧合约位于tests/legacy_workbench_fixture.py，保留参考但不作为当前业务回归；其Auth用例仍在test_auth_api.py执行。当前验证及数据库异常探针记录见[交付记录](../../docs/service/server/changelog/2026-10-16-simple-management.md)。
