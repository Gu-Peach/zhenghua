# Server 业务服务

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
