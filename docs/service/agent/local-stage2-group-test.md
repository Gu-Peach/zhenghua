# 本地 002.C / 002.M Stage 2 测试

入口：`services/agent/scripts/run_stage2_groups.py`。读取已有拆分页和图纸索引，不调用 Stage 1、不重新渲染 PDF、不创建项目、数据库客户端、队列或 Storage 上传。

默认来源目录`docs/test/agent-run-001/pages`，索引`docs/test/agent-run-001/agent/drawing_index.json`。只扫描002.C的7页和002.M的5页，跨页可读取其他本地目标页。当前本地ZH为2.0.1；旧run_stage2产物来自2.0.0，不查询远端规则包。质量修正见[记录](./changelog/2026-10-13-zh-stage2-quality.md)。

## 命令

默认只预检，不调用付费模型：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py
```

显式真实模型测试（模型标识须与服务 `/models` 返回一致，不修改 `.env`）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --allow-real-model --model "Qwen3.8 27B"
```

为保留旧结果，2.0.1对比试跑使用新输出目录（本次未执行）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --allow-real-model --model "Qwen3.8 27B" `
  --output-dir docs/test/run_stage2_v201 --run-id stage2-quality-v201
```

`--groups`、`--pages-dir`、`--index`、`--output-dir` 可覆盖默认范围；`--max-source-pages 1` 可缩小试跑，但不代表全组验收。`--run-id` 默认稳定，以便在同输出目录恢复完成页。Profile/模型/请求配置或图片改变会使旧完成页缓存失效。

双图请求默认 `--completion-max-side 3000`，复用现有缩图工具将最长边按 2 的幂次缩至上限内，仅在 `model_images/` 保存临时请求图，不改原拆分页；初扫仍使用原图。0 表示保持原图，但可能超出模型视觉预算。成功模型响应以完整请求的模型/消息/选项摘要缓存，避免页内失败恢复反复付费；不会保存请求图片 URL 或密钥。每轮调用日志使用独立目录保留错误历史。

提取已完成、仅重新导出时：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py --export-only
```

此命令不调用模型。XLSX 使用 Codex 已加载的 Node/Artifact Tool 依赖；可用 `--node`、`--node-modules` 指定已安装位置，不会在线安装依赖。导出脚本仅在被忽略的输出目录创建依赖 Junction。

## 产物

统一写入 `docs/test/run_stage2`（Git 已忽略）：

- `result.xlsx`：Sheet1，与 `1641.xlsx` 表头顺序一致的 12 列：页码、原理号、端子排、起点元件、起点描述、起点端子、终点元件、终点描述、终点端子、电流、色标、备注。色标按用户要求全部为空，不参与本次提取。
- `table.json`、`records.json`：标准行与完整结构化记录；业务备注不混入诊断原因，缺失值保持 null，不伪造电流 0。
- `page-scan-results.json`、`cross-page-tasks.json`、`cross-page-results.json`：逐页扫描和内部补全明细。
- `agent/completed-pages/`：完成页事实与恢复指纹。
- `input_manifest.json`、`run-result.json`：来源范围、执行状态、Profile/模型、调用/缓存数、usage、耗时、待复核数。服务未提供价格时成本为 null，不虚构费用。
- `model_calls/`、`model_cache/`：本地模型响应、usage 与安全错误；不记录 Authorization、密钥或完整请求消息。
- `result_preview.png`、`reference_preview.png`：表格视觉检查；`_xlsx_check/` 仅为导出器的模拟格式检查，不是真实提取结果。

参考工作簿只用于读取表头、列宽、字体和样式，标准答案内容不传入模型。起终点仍按当前图纸证据/箭头约定，不能把本次结果当成标准业务代号和排序的完全复现。未知字段与方向保留复核状态。

## 隔离与验证

脚本在构造适配器之前强制 `memory`，关闭远端包并清空 Supabase URL/service key；不实例化 Run Executor、Supabase repository 或上传器。默认冒烟禁止数据库客户端构造和 HTTP 请求，只传 Fake stages。

```powershell
.\.venv\Scripts\python.exe -m pytest services/agent/tests/smoke/test_stage2_groups_script.py `
  services/agent/tests/smoke/test_stage2_page_workflow.py -q
```

14 项离线冒烟覆盖来源范围、跨组同名图片、跨页目标、本地字段/空色标/空值与零、数据库隔离、目标页 0 占位归一化，以及 Stage 2 原有闭环边界。本次真实 12 页结果共 121 条，其中 31 条待复核；详见 [执行记录](./changelog/2026-10-13-local-stage2-groups.md)，不以此替代字段准确率验收。
