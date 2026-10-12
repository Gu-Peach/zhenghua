# Server 业务服务

真实工作台业务代码位于 `src/wiring_server`，FastAPI HTTP 入口位于 `apps/api/src/main.py`。不依赖旧 backend/frontend，不新增数据库 migration，不执行模型提取。

## 启动

仓库根目录：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir apps/api/src --host 127.0.0.1 --port 8000
```

本地可复用 `services/agent/.env` 中的 Supabase URL/service-role 和内部 Agent Token；`services/server/.env` 与进程变量优先覆盖。配置模板见 `.env.example`。生产环境单独配置，不将 service-role 或内部 Token 提供给 Web。

## 能力与边界

- 规则库新建/删除：`GET /api/v1/rule-library` 向所有已登录用户返回每个 key 的最新可用手工规则包；`POST` 基于任一未停用模板克隆新 key，确认后立即注册；`DELETE /{id}?confirmed=true` 仅创建者可执行。删除为停用，历史 checksum 保留；Improvement 隔离候选不进入规则库。共享契约见 [ADR-0012](../../docs/adr/0012-shared-ready-rule-library.md)。
- Supabase Auth 登录、JWT 在线校验、HttpOnly refresh cookie、续期与退出。
- 项目列表/创建/重命名/删除，发布后项目树，业务页/PDF 页独立。
- 项目目录按 `created_at.asc,id.asc` 固定顺序展示，选择或更新时间变化不置顶；切换时 Web 原位更新摘要，不重复拉取整个目录。
- 线表服务端分页、工作区/图纸/文字过滤、线号与原理号独立返回。
- 手工表格修改调用既有原位 RPC；before/after、record_version/revision 和幂等 receipt 保留。电压等级/端子排是同线号共享字段；页码/线号是只读索引。
- 单条端子新增/删除已接入既有表的 Server PostgreSQL 原子事务（ADR-0011）。新增归入现有线号并指定来源/跨页目标；删除归档完整记录及证据。保留空单元、其他 ID/线号/排序及结果代次，revision 递增；权限/过期拒绝/重放审计不绕过。
- 图纸签名图片地址，跨页目标查询。当前引用/target evidence 优先；缺失时完全匹配来源图纸/原理号/起点/设备并检查历史 target evidence 一致性，返回历史来源提示；有歧义拒绝猜测。
- 真实 Bucket Profile 包，文字 checksum 校验、图片签名 URL，遵循已有包 RLS。
- 内部 Agent 8100 HTTP/SSE 代理；从 JWT 强制 user_id，不接受客户端伪造身份，run/proposal/附件校验项目权限。公开计划/诊断，不转发内部推理链。

项目删除必须 owner 明确确认且没有 QUEUED/RUNNING/WAITING_INPUT 任务。先归档，再清理项目路径 Storage，最后使用已有数据库级联删除。Storage/DB 没有统一事务；中途失败项目保留为 archived，禁止业务写入，刷新后可重试删除。不要绕过 Server 直接向已归档项目创建任务。

Agent 类型确认、结果 proposal 确认、规则候选授权仍由 Agent 决策，Server 不替用户批准。当前 Agent 会话只在进程内保留；浏览器刷新可恢复现有会话/run，Agent 重启后的会话恢复不在本轮范围，已持久任务和结果仍可读取。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest services/server/tests -q
.\.venv\Scripts\python.exe apps/api/scripts/export_openapi.py
corepack pnpm --filter @wiring/web exec openapi-typescript ../api/openapi.json -o src/apis/generated.ts
```

只读真实库冒烟（显式填写项目与用户）：

```powershell
.\.venv\Scripts\python.exe services/server/tests/inspect_local_read.py --project-id <UUID> --user-id <UUID>
```

默认测试 Fake HTTP，不调用真实 VLM。真实 Auth、端子增改删/幂等/越权/过期/回滚与浏览器双图已在一次性项目验收并清理。真实 Bucket 三阶段资源面板和图纸索引已通过。用户授权后的真实浏览器上传/检测/确认已产生成功的三阶段结果（5 页/13 连接）；浏览器结果刷新/纠错/确认/归因仍待续跑，见联调记录。共享队列有其他消费者时不要运行真实队列 Fake 测试，以免任务被其他 Worker 消费。

## 端子增删的事务连接

生产配置 `SERVER_DATABASE_URL` 为 Supabase PostgreSQL 的服务端 DSN，连接角色需有既有业务表权限；不要下发浏览器。不执行 DDL，不新增 migration。没有事务连接时增删明确返回 503，既有查询和编辑不受影响。

本地已运行 Docker Supabase 时，可不用保存或打印密码：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/run_local_api.py --supabase-container supabase_db_zhenghua_test --port 8000
```

显式真实一次性验收（用户已允许临时数据）：

```powershell
.\.venv\Scripts\python.exe services/server/scripts/verify_connection_crud.py --allow-temporary-data --local-container supabase_db_zhenghua_test --browser
```

创建并清理随机 UUID 项目/账号/Storage，对真实 Auth 登录/续期、API 增改删/越权/幂等/过期/审计失败回滚及真实浏览器操作验收。不动 test0，不调用模型或向 Agent 入队。临时 API/Web 使用随机端口，仅关闭本脚本创建的进程树。真实截图在忽略的 `.runtime/real-browser/real-crud.png`，HTTP 夹具截图在 `.runtime/web-tests`。

## 显式真实模型浏览器联调

必须有用户对真实模型和一次性数据的授权；脚本通过现有 8100 服务运行，不启动或停止 Agent。正常 UI 输入保留类型/修订确认，不批准规则发布。首次运行省略 `--resume-project` 会新建项目；下面恢复已有一次性项目的成功提取，避免重复模型提取：

```powershell
$env:SERVER_ACCEPTANCE_ALLOW_REAL_MODEL="true"
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe services/server/scripts/verify_live_agent_workbench.py `
  --allow-real-model --allow-temporary-data `
  --local-container supabase_db_zhenghua_test `
  --pdf services/agent/agent_test/0.detection_test/test0.pdf `
  --resume-project 633ecd53-f4a7-50f9-be33-cc78cd4f7916
```

续跑仅允许本脚本随机创建的验收账号；密码在内存中重设，查询既有成功提取后恢复订阅。需要本地 Docker 配置读取与浏览器执行权限。仅清理该一次性账号拥有的终态项目/Storage；活跃任务保留并报告，已有 test0 不改。成功截图位于 `.runtime/real-agent/`。当前续跑尚未执行，自动审批服务配置故障需解决或由用户在自己的终端执行。
