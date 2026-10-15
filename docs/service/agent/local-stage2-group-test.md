# 本地 002.C / 002.M Stage 2 测试

2026-10-15起PDF入口和拆页入口主表均复用ZH14列输出契约，ABB/XMZ同样包含两端坐标列；业务备注只取remark，读取依据保留在记录JSON。坐标读取要求和图像expected已同步，旧结果不自动补坐标或改写。ABB1.1.4/XMZ0.1.2应使用新输出目录复测，避免混用旧Profile指纹。见[统一记录](./changelog/2026-10-15-unified-table-coordinates.md)。

入口：`services/agent/scripts/run_stage2_groups.py`。读取已有拆分页和图纸索引，不调用 Stage 1、不重新渲染 PDF、不创建项目、数据库客户端、队列或 Storage 上传。

该脚本默认绑定本地ZH，可用`--profile`切换本地规则键；模型适配器和确定性策略均按Profile.adapter绑定。其他模板资源缺失时告警后跳过，选中的规则无效仍停止。服务主入口的严格Profile加载不变，见[切换说明](./changelog/2026-10-15-local-profile-cli.md)。

默认来源目录`docs/test/pages`，索引`docs/test/pages/agent/drawing_index.json`，已按用户移动后的实际位置更新。默认只扫描002.C的7页和002.M的5页，跨页可读取其他本地目标页。当前本地ZH为2.0.5；旧run_stage2产物来自2.0.0，run_stage2_v201来自2.0.1，不查询远端规则包。[电流规则](./changelog/2026-10-15-zh-ie-current.md)允许端点冻结后沿相线读取Ie明确A值；[坐标及样例记录](./changelog/2026-10-15-zh-c01-terminal-coordinates.md)明确归一化坐标与003C01案例，元件、直接端子段及程序分类规则沿用。

## 命令

规则键为`zh`（振华）、`abb`、`zh_gantry_reel`（资源目录xmz）。使用规则键而非Prompt目录名；`--profile`只切换本地注册规则，不读取远端规则包。显式指定实验规则表示本次手工选择，不改变其发布状态。

新PDF尚未拆页时使用完整入口，自动拆页、分类和提取（替换实际PDF路径）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_page_workflow_extraction.py `
  "E:\图纸目录\其他图纸.pdf" `
  --profile zh_gantry_reel --model "Qwen3.8 27B" `
  --max-pdf-pages 0 --output-dir docs/test/run_xmz_001 `
  --run-id xmz-001 --allow-real-model
```

0表示全PDF；可改为较小正整数限制物理页数。完整入口输出根目录`table.xlsx`和分阶段JSON，以及`pages/`和`agent/drawing_index.json`。内存/本地模式已强制设置，不依赖.env中的持久化模式，不上传或调用业务数据库。

已有拆页和索引时，可切规则只跑指定工作区：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --profile zh_gantry_reel --model "Qwen3.8 27B" `
  --pages-dir docs/test/run_xmz_001/pages `
  --index docs/test/run_xmz_001/agent/drawing_index.json `
  --groups GCR.1 --output-dir docs/test/run_xmz_stage2_001 `
  --run-id xmz-stage2-001 --allow-real-model
```

`--groups`必须使用该索引内实际工作区，图片目录和索引必须来自同一PDF。变更PDF/规则时使用新输出目录和run-id；完整入口的表格含诊断列，分组入口生成下述标准14列`result.xlsx`。

默认只预检，不调用付费模型：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py
```

显式真实模型测试（模型标识须与服务 `/models` 返回一致，不修改 `.env`）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --allow-real-model --model "Qwen3.8 27B"
```

为保留旧结果，2.0.2对比试跑使用新输出目录（本次未执行，用户自行运行）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --allow-real-model --model "Qwen3.8 27B" `
  --output-dir docs/test/run_stage2_v202 --run-id stage2-direct-v202
```

`--groups`、`--pages-dir`、`--index`、`--output-dir` 可覆盖默认范围；`--max-source-pages 1` 可缩小试跑，但不代表全组验收。`--run-id` 默认稳定，以便在同输出目录恢复完成页。Profile/模型/请求配置或图片改变会使旧完成页缓存失效。

双图请求默认`--completion-max-side 0`，关闭额外的前置缩放，统一按输入图优先的像素预算处理。0不代表绕过预算：实际图仍受`AGENT_MODEL_INPUT_MAX_IMAGE_SIDE`及总像素上限约束；Few-shot先压缩到`AGENT_MODEL_FEWSHOT_MIN_IMAGE_SIDE`下限，仍超预算则整组删例，实际图自身超预算才缩小它。显式设置`--completion-max-side`仍可额外预缩放。原拆分页不改，坐标保持归一化。

成功响应按模型/消息/选项摘要缓存；图像预算策略与配置也进入完成页指纹，变更后不会复用旧完成页。复测使用新输出目录。`model_calls`记录实际发送尺寸、保留/删除案例数和是否因总预算缩小实际图，不保存请求图片URL或密钥。每轮日志使用独立目录保留历史。

提取已完成、仅重新导出时：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py --export-only
```

此命令不调用模型。XLSX 使用 Codex 已加载的 Node/Artifact Tool 依赖；可用 `--node`、`--node-modules` 指定已安装位置，不会在线安装依赖。导出脚本仅在被忽略的输出目录创建依赖 Junction。

## 产物

统一写入 `docs/test/run_stage2`（Git 已忽略）：

- `result.xlsx`：Sheet1，前12列沿用 `1641.xlsx`：页码、原理号、端子排、起点元件、起点描述、起点端子、终点元件、终点描述、终点端子、电流、色标、备注；再追加起点端子坐标、终点端子坐标，共14列。色标按用户要求全部为空。坐标保存JSON对象，例如`{"x":0.178,"y":0.173,"pdf_page_number":403}`，左上角为原点、整图归一化0～1，各端绑定各自图片物理页；未知留空，不修改参考模板。
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
## 模型输出诊断补充（2026-10-15）

PDF入口每次调用的响应保存在本次输出目录`model_calls/*.json`，包括`response_content`、`response_char_count`、`finish_reason`、`usage`与阶段/图片尺寸metadata。此文件只表示服务端返回，不表示内部JSON通过；不记录请求图片或认证，不写数据库。`finish_reason=length`配合不完整JSON可确认长度受限；缺失原因时不能仅看解析位置猜截断。ABB现在也收到共享JSON Schema，ZH特有说明仍隔离；不自动开启服务商JSON模式或增加token额度/付费重试次数。
