# 业务 API

FastAPI 入口 `src/main.py`，领域/持久化代码属于 `services/server`。默认端口 8000；独立 Agent 保持 8100。启动与接口说明见 [Server README](../../services/server/README.md)。OpenAPI 生成物在 `openapi.json`，Web 生成类型在 `apps/web/src/apis/generated.ts`。

所有业务接口要求 Supabase access JWT；禁止用用户 UUID 代替鉴权。浏览器经 `/api/v1` 请求，服务端将已校验身份转发 Agent。不新增数据库表，不引用旧 `backend` API。

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
