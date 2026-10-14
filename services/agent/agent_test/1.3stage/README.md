# 阶段 1 / Gate B：纯 HTTP 终端验收

链路：业务上传创建项目/私有原 PDF → Supervisor 首页识别 → 终端人工确认 → 入队 → Worker 三阶段逐轮持久化/读库 → SSE → 固定结果版本查询。脚本只用 stdlib/httpx，不导入 Agent/tool/VLM/Supabase，不推进 stage。

## 前置

本地 Supabase 已应用到 `20261011000000`，服务端 `services/agent/.env` 配好模型、Supabase 和私有 `project-assets`。仅 ZH 全量提取启用；ABB experimental 可检测，不可正式提取。需已有 Supabase Auth 用户 UUID（本地 Studio 的 Authentication → Users → User UID），不能再用阶段 0 的 `acceptance-terminal` 字符串。脚本不创建用户，不读取 service-role key 或服务端 .env。

让服务加载新代码；不要同时启动两个监听 8100 的服务。开发验收可在服务终端启动同进程 Worker：

```powershell
$env:AGENT_PERSISTENCE_BACKEND="supabase"
$env:AGENT_INLINE_WORKER="true"
.\.venv\Scripts\python.exe -m uvicorn src.main:app `
  --app-dir services/agent --host 127.0.0.1 --port 8100
```

inline Worker 只用于本地开发，生产长任务应独立部署；没有运行 Worker 时任务保持 QUEUED，脚本不会代替服务执行提取。旧三阶段 CLI 不具备本验收链路，不要用它代替 HTTP 脚本。

## 执行

另开终端，从仓库根目录：

```powershell
$env:AGENT_ACCEPTANCE_ALLOW_REAL_MODEL="true"
$env:AGENT_ACCEPTANCE_USER_ID="<已有 Supabase Auth 用户 UUID>"
# 若服务配置了内部 token，此终端设置同一 AGENT_INTERNAL_TOKEN；不要粘贴到报告。
.\.venv\Scripts\python.exe "services/agent/agent_test/1.3stage/run_acceptance.py" `
  "services/agent/agent_test/1.3stage/<测试PDF>.pdf" `
  --base-url http://127.0.0.1:8100
```

不传 PDF 则从目录中的 PDF 选择。回答 `确认` / `OK` 或指定正确类型；`/quit` 在提取前退出。任务入队后断开客户端不会取消任务。可用 `--max-wait` 控制监看时长；已创建任务的恢复监看：

```powershell
.\.venv\Scripts\python.exe "services/agent/agent_test/1.3stage/run_acceptance.py" `
  --run-id "<agent_run_id>" --user-id "<同一用户 UUID>"
```

`--run-id` 只查询/监听，不上传、不创建新 run，不需要短期会话还在。FAILED/CANCELLED 不会自行重跑，WAITING_INPUT/NEEDS_REVIEW 明确展示，取消/恢复仍使用受控 run API。

服务端对同一业务 import 固定完整提取 key：原上传 key 重传/服务重启后再确认只复用旧 run，不重新入队、不改原确认。新一次提取应新建 import/key；脚本默认每次生成新 key，因此恢复监看务必用 `--run-id`，不要再次不带 run ID 运行以免新建项目。

## 报告与判定

默认报告写忽略目录 `runs/<时间-会话>/transcript.json`、`summary.json`，包含项目/run ID、模型、案例、阶段提交摘要/耗时、结果字段和终态。接口未提供 usage/费用时为 unknown/null，不记假零。Stage 耗时为持久事件的时间跨度（包含重试/中断），不是单次模型调用时长。

可用 `--expected <人工确认的预期扁平行JSON>` 比较字段，数组按接口的 wire_number/core_order/connection_id 顺序对齐。预期行只写要检查的字段，例如线号、起点/终点、业务页、跨页状态；不必写自动 UUID。行数与字段差异分别报告。无人工 baseline 时为 manual_review_required；exit 0 仅表示 HTTP 执行完毕，不能代替准确率验收通过。NEEDS_REVIEW 保留人工复核要求。

默认离线测试不调用真实模型：

```powershell
.\.venv\Scripts\python.exe -m pytest services/agent/tests/integration/test_gate_b_http.py
```

显式本地 Supabase/Fake 模型测试会创建并清理自己唯一的用户/项目/Storage 对象，要求队列没有其他待处理任务：

```powershell
$env:AGENT_TEST_REAL_SUPABASE="true"
.\.venv\Scripts\python.exe -m pytest services/agent/tests/integration/test_gate_b_real_supabase.py
```

该接口仅供内部 Server/受控终端验收，不是 Web JWT API；Web、成员权限代理和真实模型字段基线另行验收。
