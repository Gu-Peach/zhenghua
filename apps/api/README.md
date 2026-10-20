# 业务 API

API2.16.0新增当前项目/工作区/图纸/搜索范围一键审核，含所有分页、版本/权限/原子确认；OpenAPI/生成类型同步，本地20261020020000已安装。重载8000刷新Web，见[交付](../../docs/apps/api/changelog/2026-10-20-bulk-review.md)。

API2.15.0新增人工复核POST路由和needs_review_count，OpenAPI/Web生成类型同步。本地20261020010000迁移已安装，重载8000并刷新Web生效，本轮无8100/Worker变更，见[交付](../../docs/apps/api/changelog/2026-10-20-connection-review.md)。

API2.14.0同步重扫requirements DTO/OpenAPI，历史任务可缺省，新Explain模型工具要求完整需求并校验范围/字段能力。无新路由或migration；先重载8000，再加载8100/实际Worker与刷新Web新建任务，见[契约交付](../../docs/apps/api/changelog/2026-10-20-rescan-requirements.md)。

API2.13.0新增主助手历史删除 `DELETE /api/v1/assistant/conversations/{conversation}`，成功返回204。需新增20261019050000迁移，本地已安装且当前8000已加载2.13.0，刷新Web即可；无8100/Worker变更。见[交付](../../docs/apps/api/changelog/2026-10-19-assistant-history-delete.md)。

API2.10.0同步范围替换DTO与确认门禁：只接收checksum/accepted，实际删除/写入来自持久化候选，数据库能力缺失则拒绝。新迁移本地已安装且业务表未变；重载8000、8100/Worker、刷新Web并新建任务。见[事务交付](../../docs/service/server/changelog/2026-10-19-rescan-scope-replacement.md)。

API2.9.0新增项目根范围XLSX下载，OpenAPI已定义二进制媒体类型和客户端契约；ExplainTurn同步allow_rescan，普通自动解释由前端传false。按下方原命令重新加载8000及8100，无新迁移、端口或生产依赖，刷新前端即可使用。见[Server交付](../../docs/service/server/changelog/2026-10-18-project-export.md)。

API2.8.0提供项目级`rescan-assets`与`rescans`接口，浏览器只访问8000。先部署`20261018050000_explain_rescan.sql`，再按下方命令重新加载8000、[8100及独立Worker](../../services/agent/README.md)。上传细节图不修改规则，重扫候选确认后才事务提交。契约仍由`export_explain_contract.py`→`export_openapi.py`→Web的openapi-typescript生成。见[接口与事务](../../docs/service/server/changelog/2026-10-18-explain-rescan.md)。

API2.7.1同步Explain的answer_reset公开事件。重载8000/8100与刷新前端后可撤回无真实方案的口述预览，补调失败明确报错；无需新增数据库迁移。

API2.7.0增加`GET /api/v1/projects/{project}/connection-edits`及按proposal读取和`POST .../{proposal}/decision`。只接受checksum和accepted，实际修改来自持久方案并由Server事务确认。本项目本地已应用`20261018020000_explain_connection_edits.sql`，其他环境须先应用；加载8000/8100新代码，沿用下方启动方式。此轮未改真实线表。

当前API2.6.0增加规则编辑草稿、手动保存、建议确认/工具流及新版替换发布，需加载8000和8100新代码。发布替换/安全回收迁移`20261018010000`已在本项目本地库部署，其他环境需要先应用；启动命令和环境变量沿用下方。见[编辑与替换记录](../../docs/service/server/changelog/2026-10-18-profile-editing-replacement.md)。

API2.5.0已提供`POST /api/v1/profile/drafts/{draft}/pdf-samples`，用于规则第一阶段随机两页分类；沿用原有启动参数。见[PDF抽样记录](../../docs/service/server/changelog/2026-10-17-profile-pdf-sampling.md)。

2026-10-17规则聊天入口需当前API2.4.0：`/api/v1/profile/drafts/{draft}/conversation`及其`/turns/stream`。使用下方原命令重新加载8000，并加载8100新增Agent代码；没有新增启动参数/端口/迁移。见[对话代理记录](../../docs/service/server/changelog/2026-10-17-profile-conversation.md)。

2026-10-17规则创建/发布接口属于当前API 2.3.0。前端“新建草稿”或读取草稿返回`404 Not Found`时，先检查`http://127.0.0.1:8000/openapi.json`是否包含`/api/v1/profile/drafts`。若仍显示2.2.0且没有该路径，需要在原终端Ctrl+C停止后，按下方原启动方式重新启动8000加载代码；仅刷新前端或重启8100不会加载业务API的新路由。不要为此重复启动Worker。此次排查确认8100已有草稿路由，8000仍为旧版本；3项Mock发布/创建链路测试通过，未操作运行服务或业务数据。

2026-10-17版本2.2.0新增JWT鉴权Explain流式代理，浏览器经8000转发到8100共享Agent宿主；工具/图纸事件契约和生成TS已同步。无数据库Schema变化，启动及配置见[Server README](../../services/server/README.md)，实现见[交付](../../docs/service/server/changelog/2026-10-17-explain-proxy.md)。

2026-10-16已增加上传入队、提取进度/SSE/重试接口和增量结果字段；先应用新增迁移，再重载本服务并启动[提取Worker](../../services/agent/README.md#当前增量提取的启动方式)。本地zhenghua_test库现已部署该迁移，当前8000 API已核对为2.1.0。API仍是8000，浏览器不直接请求Worker。见[Server交付](../../docs/service/server/changelog/2026-10-16-incremental-extraction.md)。较早的“上传不提取”段落仅记录上一次交付。

2026-10-16当前入口为三表数据管理API v2：项目/规则引用/PDF登记、JSON图纸预览、批次线表及行级CRUD已接入。无需启动Agent；上传不自动提取，旧Supervisor/纠错/规则发布入口退出当前契约。请重新启动8000后端加载新路由，详见[Server说明](../../services/server/README.md)和[接入记录](../../docs/service/server/changelog/2026-10-16-simple-management.md)。下文Agent联调/直连数据库命令为旧运行方式，本轮不需要。

FastAPI 入口 `src/main.py`，领域/持久化代码属于 `services/server`。默认端口 8000；独立 Agent 保持 8100。启动与接口说明见 [Server README](../../services/server/README.md)。OpenAPI 生成物在 `openapi.json`，Web 生成类型在 `apps/web/src/apis/generated.ts`。

所有业务接口要求 Supabase access JWT；禁止用用户 UUID 代替鉴权。浏览器经 `/api/v1` 请求；Server校验所有者后读写三表，不引用旧 `backend` API。

## 本地启动

以下命令使用 Windows PowerShell，从仓库根目录执行；克隆路径不同时调整 `Set-Location`。首次准备 Python 3.10+ 环境和依赖：

```powershell
Set-Location E:\project\zhenghua_test
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -e services/server
if (-not (Test-Path services\server\.env)) { Copy-Item services\server\.env.example services\server\.env }
```

按 [Server 配置说明](../../services/server/README.md#启动) 填写 `services/server/.env` 后启动：

```powershell
Set-Location E:\project\zhenghua_test
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

使用已启动的本地 Docker Supabase、需要端子增删事务连接时，改用以下命令（与上面的命令二选一）：

```powershell
Set-Location E:\project\zhenghua_test
.\.venv\Scripts\python.exe services/server/scripts/run_local_api.py --supabase-container supabase_db_zhenghua_test --port 8000
```

接口文档：`http://127.0.0.1:8000/docs`；探活：`http://127.0.0.1:8000/health`。完整联调按 [Agent](../../services/agent/README.md#启动) → 本 API → [Web](../web/README.md#启动) 的顺序，在独立终端启动。停止当前服务使用 `Ctrl+C`。
