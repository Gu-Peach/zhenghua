# 电气原理图 VLM 提取后端

这个后端使用 OpenAI Chat Completions 兼容格式调用 VLM，读取电气原理图图片或 PDF，并把 prompt 返回的 JSON 记录写入 xlsx 放线表。

当前还包含一个 React + Vite 前端管理应用：上传 PDF 后，后端会先把 PDF 拆成页图，再用视觉模型对页面归类，最后按线表批次提取结果并保存到 `frontend/public/library` 管理库文件夹。

当前 PDF 主流程使用 LangGraph V1 Agent：`pdf_to_images -> segment -> extract_wiring -> assemble_xlsx`。`segment` 对每一对相邻原图并发调用 VLM，只依据项目号 `Project.NR` 和图号前缀判断是否合并，并用并查集生成段。每段会继续调用 VLM 提取放线表，最后写出每段的 JSON/XLSX 和分段诊断日志。

如果启用 Supabase，Agent 完成后会把当前 job 文件夹递归上传到 `images` bucket，并把每个线表批次 upsert 到 `public.wiring_tables`。前端配置 Supabase anon key 后会直接查询这张表，文件通过 Storage 公开 URL 访问。

## 目录结构

```text
backend/
  app/
    api/routes/        # FastAPI 路由
    core/              # 配置与环境变量
    prompts/           # VLM prompt，当前为 few-shot 版本
      examples_extration/ # 放线表提取 few-shot 案例
      example_segment/    # 相邻页分段 few-shot 案例
    schemas/           # Pydantic 入参/出参模型
    services/          # VLM 调用、文件转换、xlsx 生成等业务逻辑
    main.py            # 应用工厂
    cli.py             # 命令行入口实现
  main.py              # 兼容 uvicorn backend.main:app
  cli.py               # 兼容 python -m backend.cli
  test_case/           # 本地测试案例，每个子目录一个案例
  requirements.txt
frontend/              # React + Vite 前端，public/library 作为临时管理库
```

## 配置

```powershell
Copy-Item backend/.env.example backend/.env
```

然后编辑 `backend/.env`：

```env
VLM_MODEL=your-vlm-model
VLM_BASE_URL=http://3stooges.chat:4088
VLM_API_KEY=your-api-key
```

后端会自动读取项目根目录 `.env` 和 `backend/.env`。真实系统环境变量优先级最高，命令行或接口表单传入的 `model/base_url/api_key` 可以临时覆盖。

`VLM_BASE_URL` 写服务根地址即可，例如 `http://3stooges.chat:4088`。后端会自动调用 `http://3stooges.chat:4088/v1/chat/completions`。如果你的服务不是这个路径，可以配置 `VLM_CHAT_COMPLETIONS_URL` 写完整地址。

默认系统 Prompt 为 `backend/app/prompts/zh/page_scan_index.md`。页面分类和跨页补全分别使用同目录下的 `page_classification.md` 与 `page_cross_page_completion.md`；可通过对应环境变量临时覆盖。

中文 Prompt 与 Few-shot 资源统一存放在 `backend/app/prompts/zh/`。当前 Stage 2 和 Stage 3 共享 `backend/app/prompts/zh/examples_wiring/002c/manifest.json`；页面分类样本位于 `backend/app/prompts/zh/examples_page_classification/`。各目录通过 `manifest.json` 记录图片、结构化输入和标准答案。

可选配置：

```powershell
VLM_TIMEOUT_SECONDS=300
VLM_RETRY_COUNT=2
VLM_RETRY_BACKOFF_SECONDS=2
VLM_RETRY_MAX_BACKOFF_SECONDS=30
VLM_MAX_PDF_PAGES=0
VLM_REFERENCE_TARGET_LIMIT=4
VLM_CONCURRENCY=1
VLM_IMAGE_BATCH_SIZE=4
VLM_GROUPING_IMAGE_BATCH_SIZE=8
VLM_PDF_RENDER_DPI=300
VLM_LIBRARY_ROOT=frontend/public/library
VLM_ENABLE_THINKING=false
VLM_USE_RESPONSE_FORMAT=false

SUPABASE_ENABLED=false
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=your-local-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-local-service-role-key
SUPABASE_STORAGE_BUCKET=images
```

旧版图片提取接口使用 `VLM_IMAGE_BATCH_SIZE` 控制一次请求的图片数。LangGraph V1 的 `segment` 固定逐对发送相邻原图，`extract_wiring` 按完整段发送 1 到 N 张图。

LangGraph 分段相关配置：

```env
VLM_SEGMENT_CONCURRENCY=4
VLM_SEGMENT_RETRY_COUNT=1
VLM_MAX_SEGMENT_PAGES=20
VLM_KEEP_TEMP_IMAGES=false
VLM_OUTPUT_MODE=library
# VLM_IMPORT_XLS_TEMPLATE_PATH=test_case/放线表导入格式(1).xls
# VLM_TERMINAL_STRIP_MAP={"XD3":"X3","XD4":"X4"}
```

如果执行时出现 `ReadTimeout`，优先把 `VLM_TIMEOUT_SECONDS` 调大，例如 `600`。如果服务对多图请求较慢，可以临时把 `VLM_IMAGE_BATCH_SIZE` 改成 `1`，但跨页案例的准确率可能下降。

Qwen3 等推理模型默认可能会先生成大量 thinking 内容，导致图纸请求耗时很长。当前推荐设置 `VLM_ENABLE_THINKING=false`，后端会通过 `chat_template_kwargs.enable_thinking=false` 传给 OpenAI 兼容服务。

## 启动

```powershell
pip install -r backend/requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

前端开发模式：

```powershell
cd frontend
npm install
npm run dev
```

开发模式打开：

```text
http://localhost:5173/
```

生产构建：

```powershell
cd frontend
npm run build
```

构建后由 FastAPI 托管，打开：

```text
http://localhost:8000/
```

前端包含两个页面：

- `处理页`：上传 PDF，执行拆页、归类、提取、落库。
- `管理页`：查看历史处理文件夹，打开原始 PDF、JSON 和 XLSX。

## 接口

PDF 完整处理并写入管理库：

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/process/pdf" `
  -F "file=@drawing.pdf"
```

管理库列表与详情：

```http
GET /api/v1/library
GET /api/v1/library/{job_id}
DELETE /api/v1/library/{job_id}
```

管理库文件夹结构：

```text
frontend/public/library/{job_id}/
  manifest.json
  source/{原始PDF}
  pages/page_001.png
  groups/wire-table-001/pages/page_001.png
  groups/wire-table-001/source-pages.json
  groups/wire-table-001/records.json
  groups/wire-table-001/wiring-table.xlsx
```

旧版图片/多文件提取接口仍可用：

提取 JSON：

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/extract/wires" `
  -F "files=@drawing.png" `
  -F "model=your-vlm-model"
```

直接下载 xlsx：

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/extract/wires/xlsx" `
  -F "files=@drawing.png" `
  -F "model=your-vlm-model" `
  -o wiring-table.xlsx
```

只把已有 JSON 导出为 xlsx：

```http
POST /api/v1/wires/xlsx
Content-Type: application/json

{
  "records": [
    {
      "line_number": "003G0121",
      "core_number": 1,
      "color": "蓝",
      "spec": "12X1.5",
      "start_location": "+01F11.3",
      "start_device": "-XD3",
      "start_terminal": "3",
      "end_location": "+01F26",
      "end_device": "-AIM1",
      "end_terminal": "X3:3",
      "terminal_strip": "X3",
      "remark": "24VDC+",
      "confidence": 0.95,
      "source_note": "终点依据关联参考 =.C+01F26/1.3"
    }
  ]
}
```

输出 xlsx 包含两个 sheet：`放线表` 使用样例表头，`原始提取` 保存 prompt 原字段和原始 JSON，便于追溯。

命令行处理：

```powershell
python -m backend.cli drawing_page_1.png drawing_page_2.png `
  -o outputs/wiring-table.xlsx `
  --model your-vlm-model
```

## 执行测试案例

`backend/test_case` 下每个子文件夹是一个独立案例。执行下面命令后，每个案例目录会生成：

- `result.json`：VLM 原始结构化提取结果。
- `result.xlsx`：按放线表表头整理后的表格。

如果某个案例失败，该案例目录会生成 `result.error.json`，里面包含失败原因，其他案例会继续执行。

```powershell
python -m backend.cli --test-case-dir
```

直接运行 LangGraph Agent：

```powershell
python -m backend.cli --agent-pdf drawing.pdf -o outputs/wiring-table.xlsx --agent-output-mode single_xlsx
```

详见 `backend/app/agents/README.md`。

Supabase 建表和 bucket 迁移在 `supabase/migrations/20260918000000_create_wiring_tables.sql`。本地启动 Supabase 后执行：

```powershell
supabase db reset
```

然后将 `supabase start` 输出的 anon key 写入 `frontend/.env.local`，将 service-role key 写入 `backend/.env`，并设置 `SUPABASE_ENABLED=true`。详细说明见 `supabase/README.md`。

执行时 CLI 会持续打印进度，包括当前案例、图片数量、VLM batch、endpoint 和 timeout。最终 JSON 汇总仍输出到标准输出；进度信息输出到标准错误，方便排查长时间推理。

也可以指定其他目录或输出文件名：

```powershell
python -m backend.cli --test-case-dir backend/test_case --case-output-name vlm_result
```
# Agent pipeline notes

The PDF workflow is `pdf_to_images -> drawing_index/segment -> extraction batches -> assemble_xlsx`.
For EPLAN PDFs the text layer builds `agent/drawing_index.json` and resolves
cross-page references before the VLM call. Each extraction batch contains one
source page and at most `VLM_REFERENCE_TARGET_LIMIT` target pages. Unresolved
or `FOR DETAIL SEE ...` references are retained as external/needs-review
evidence; the model must not invent an endpoint.

Set `VLM_MAX_PDF_PAGES=0` for full-document processing (the default). Use
`VLM_KEEP_TEMP_IMAGES=true` when inspecting rendered pages. Each library job
stores `agent/merge_decisions.json`, `segments.json`, `extraction_batches.json`,
`drawing_index.json`, `errors.json`, and `validation-warnings.json`.

The downstream import workbook is a legacy `.xls` layout. Install the backend
requirements including `xlwt` to generate `wiring-table-import.xls`; the
ordinary `.xlsx` output remains available for preview. The import columns are
the template's first twelve columns: page, line number, voltage/terminal strip,
start code/description/terminal, end code/description/terminal, current,
remark, and color.

For a direct CLI run use `python -m backend.cli --agent-pdf <input.pdf> -o
outputs/wiring-table.xlsx`. This produces the preview workbook and
`outputs/wiring-table-import.xls`; the web upload uses the same writer inside
each `frontend/public/library/<job>/groups/<group>/` folder.

To test the real HTTP backend flow and collect step artifacts, start uvicorn
and run:

```powershell
python scripts/test_backend_pipeline.py case/input.pdf `
  --output-dir test_case/backend-result
```

The script uploads the PDF, polls the job, prints status changes, and downloads
`agent/progress.jsonl`, `drawing_index.json`, `extraction_batches.json`,
`segments.json`, `merge_decisions.json`, errors/warnings, group results, and
the final `wiring-table-import.xlsx` plus native `wiring-table-import.xls`.

Each extraction batch is checkpointed in `agent/extraction-checkpoint.json`.
After a provider outage, resume the same job instead of uploading the PDF again:

```powershell
python scripts/test_backend_pipeline.py --resume-job-id <job_id> `
  --output-dir test_case/backend-result-resumed
```

The backend resume endpoint is `POST /api/v1/library/{job_id}/resume`.
Already completed batches are reused; failed or unfinished batches are retried.
The client downloader also retries temporary connection failures.

To test provider concurrency with a small image request:

```powershell
python scripts/probe_vlm_concurrency.py --levels 1 2 4
```

## Processing order

The graph has three Agent stages after page classification. `page_scan_loop`
receives only one source page at a time and writes same-page table values;
cross-page rows keep their references and an empty endpoint. The deterministic
`build_cross_page_tasks` node then resolves each row's
`Plant Function + Page Number + Column` reference and writes one task per row.
`resolve_cross_page` sends that row's source page and resolved target pages to
the third Agent, which fills the endpoint or returns `needs_review`.

The stage-two table and third-stage task/checkpoint artifacts are written under
`agent/stage2-table.json`, `agent/cross-page-tasks.json`, and
`agent/cross-page-checkpoint.json`. `VLM_REFERENCE_TARGET_LIMIT` limits the
number of target pages attached to one row-level task.
