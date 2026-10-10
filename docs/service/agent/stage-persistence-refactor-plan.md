# 三阶段提取：阶段性持久化改造方案

日期：2026-10-10。修订：V1.1（已纳入六项一致性评审意见）。状态：**方案待评审，尚未实施**。

适用范围：正式 `FULL_EXTRACTION` Worker 的三阶段提取。验收目录 `agent_test/1.3stage` 指整个三阶段链路，本文 Stage 1 专指其中的页面分类 Agent。设计依据见 [ADR-0007](../../adr/0007-durable-extraction-stage-boundaries.md)。

## 1. 目标与当前差距

目标：每个模型处理项完成后立即提交结构化结果；整个阶段完成后提交持久化清单；下一阶段只读取已提交清单和对应数据库结果，不能依靠上一阶段遗留的 Graph 内存或本地 JSON。

当前情况（源码核对，非线上数据库现场审计）：

- `graphs/document_extraction/workflow.py` 在一次 Graph 中传递 `GraphState`；页面分类、扫描和跨页补全共享状态。
- `pages.py` 和 `cross_page.py` 写本地 JSON/checkpoint，恢复也主要读取这些文件。
- `FullExtractionRunExecutor.consume_progress()` 根据日志队列上传文件、登记 Artifact 和发布阶段完成事件，但 Graph 不等待这个队列完成持久化，缺少阶段屏障。
- Stage 1 的 `workspaces/drawings` 和图片已具备发布能力；Stage 2/3 数据主要是 Storage 文件引用，而非下一阶段直接消费的数据库项。
- `AgentWorker` 在完整提取结束后提交 Proposal 和规范化结果版本。最终线表落库能力应保留，不重写。
- `AgentWorker.run_once()` 目前只接受 `QUEUED`；崩溃遗留的 `RUNNING` run 可能被过期租约接管后直接 acknowledge，现有队列不等于完整跨进程恢复。结果 RPC、result-version Artifact、run 终态和完成事件也存在分步提交故障窗口。

本轮方案不改 Prompt、Few-shot、识别算法、`is_cross_page` 含义或最终线表的业务字段；不实施 migration、不调用真实 VLM、不停止运行进程。

## 2. 目标流程和阶段边界

```text
上传业务 PDF、登记 document_files、确认并冻结 Profile
  ↓
Render：逐页上传图片并提交页面项 → 提交渲染清单
  ↓ 从数据库重新加载渲染清单
Stage 1：逐页提交未发布分类投影 → 封存分类清单 → 原子发布项目树
  ↓ 从数据库重新加载分类清单、页面项和图片引用
Stage 2：逐页扫描并提交 → 归一化/合并 → 提交扫描清单
  ↓ 从数据库读取扫描结果和分类索引
Build tasks：确定性解析跨页引用 → 提交任务项/任务清单
  ↓ 从数据库读取任务清单及指定页面
Stage 3：逐任务补全并提交 → 提交跨页结果清单
  ↓ 从数据库重建结果，应用受控补全
Validation → 持久化校验结果 → Proposal → 原子提交结果版本
  ↓
读取已提交结果 receipt → 幂等原子收尾（Artifact/终态/事件）
```

每个箭头都是 `await` 的持久化屏障。阶段间只传 `run_id + snapshot_artifact_id`，阶段内部可用内存缓存；缓存与数据库不一致时以已提交快照为准。

V1 先采用全阶段屏障：Stage 1 全部页面处理完后才进入 Stage 2，Stage 2 清单封存后才生成 Stage 3 任务。不同时引入页面流水线或跨阶段并发。

## 3. 保存位置：复用现有表，不增加三张阶段业务表

| 对象 | 权威位置 | 作用 |
| --- | --- | --- |
| 原始 PDF | `document_files` + 私有 `project-assets` | 输入身份、checksum、原文件 |
| 未发布分类投影 / 已发布工作区和图纸 | run-scoped `agent_artifacts` / `workspaces`、`drawings` + 项目发布指针 | 逐页项不覆盖共享项目树；Stage 1 封存后原子发布 |
| 每页分类/扫描、每个跨页任务和补全结果 | `agent_artifacts.payload` JSONB | 强类型、不可变处理项，可按 run/stage/item 查找 |
| 阶段清单、归一化快照、校验结果 | `agent_artifacts.payload` JSONB | 下一阶段的固定输入，不是扫描本地目录 |
| 处理游标、当前阶段清单指针 | `agent_checkpoints.payload` | 可变 head；CAS revision 控制并发，不承担大结果集合 |
| 失败尝试/模型消耗 | `agent_artifacts` 尝试记录、现有 Model Trace、`agent_events` | 失败历史不被重试抹除；费用缺失记 null |
| 图片、原始响应大文件、JSON 诊断副本、XLSX | 私有 `project-assets` | 大对象；数据库存引用和 checksum，不存 Base64 |
| 最终结果 | `result_versions/wiring_units/wiring_connections/connection_evidence` | 经过校验的业务结果，不混入未完成阶段数据 |

核心业务字段仍是可查询列；阶段 payload 是内部执行结果，不能用它替代最终线表。`wiring_connection_rows` 是现有结果检索视图，不是阶段写入表。

实际写入 `agent_artifacts` 时：`artifact_id` 是物理产物 ID，`agent_run_id` 关联现有 run，`kind` 区分 `extraction_stage_item/extraction_stage_manifest/extraction_stage_aggregate/extraction_stage_attempt`，`payload` 放以下结构，顶层 `checksum` 存完整记录摘要，payload 的 `result_digest` 存业务结果摘要（见 4.8）。纯数据库 JSON 项的 `storage_bucket/storage_path` 均为 null；有 Storage 诊断副本时二者同时填写，遵守现有 storage-pair CHECK，不能只写 bucket 不写 path。图片引用留在类型化 payload 中，不误用本地文件名代替对象键。

`agent_artifacts` 当前不可变写入语义继续保留。新增类型通过 Pydantic discriminated union 校验，不继续传播任意 `dict[str, Any]`。标准化项同时在新增索引列暴露 `stage/item_id/kind/schema_version/input_fingerprint`，避免每次加载整 run 的 JSONB。

## 4. 每轮提交的公共结构

“一轮”在 Stage 1/2 是一张 PDF 物理页，在 Stage 3 是一个指定目标页的跨页任务；不是 Supervisor 的聊天回合。空白页和非线表页也提交跳过项，防止恢复时重新调用模型。

拟新增 `StageItemEnvelope`，其逻辑结构如下（UUID、checksum、时间为结构示意，实际必须通过类型校验）：

```json
{
  "schema_version": "1.0.0",
  "agent_run_id": "<run-uuid>",
  "project_id": "<project-uuid>",
  "source_document_id": "<document-uuid>",
  "source_checksum": "sha256:<pdf-digest>",
  "profile": {"key": "zh", "version": "<frozen-version>", "checksum": "sha256:<profile-digest>"},
  "stage": "PAGE_SCAN",
  "item_id": "pdf-page:3",
  "attempt": 1,
  "input_refs": [
    {"artifact_id": "<classification-item>", "checksum": "sha256:<digest>"}
  ],
  "input_fingerprint": "sha256:<inputs-and-config-digest>",
  "result_digest": "sha256:<semantic-result-digest>",
  "status": "completed",
  "needs_review": false,
  "result": {},
  "metrics": {
    "model": "<actual-model>",
    "duration_seconds": 2.1,
    "model_attempts": 1,
    "usage": null,
    "cost": null
  },
  "raw_response_ref": null,
  "error": null,
  "created_at": "<UTC timestamp>"
}
```

- `stage` 复用现有 `AgentStage`；`result` 按 stage 选择类型。页/任务 ID 由系统生成，模型不能指定数据库 ID。
- `status` 是处理项执行状态：`completed/skipped/failed`，不是端子跨页状态；`needs_review` 独立表示字段不确定。
- 成功结果只发布一次。物理 Artifact ID 包含输入指纹和 attempt；checkpoint head 指向选中的成功项。相同输入及相同 `result_digest` 返回原成功 receipt；相同输入但不同结果按 4.8 记录冲突，不覆盖 canonical 成功项。
- 输入指纹覆盖上游 Artifact checksum、图片 checksum、Profile/Prompt/Few-shot/Schema/校验器版本、实际模型和生成配置。输入改变时建立新 run，不默默复用旧成功项。
- `result` 中只保存该项结果；模型原始响应可另存私有对象，引用不能是签名 URL、本地绝对路径或鉴权信息。
- 摘要使用 4.8 的三个不同目的：输入身份、业务结果去重、完整记录校验。`attempt/error/metrics` 不参与业务结果摘要，但参与完整记录摘要。

### 4.1 渲染项

`item_id=pdf-page:<物理页号>`。result 至少包含：

```json
{
  "pdf_page_number": 3,
  "image": {
    "storage_bucket": "project-assets",
    "storage_path": "projects/<project>/runs/<run>/render/page-0003/<image-sha256>.png",
    "checksum": "sha256:<image-digest>",
    "mime_type": "image/png",
    "width": 3508,
    "height": 2480,
    "render_dpi": 300
  },
  "blank": false,
  "page_text_ref": null
}
```

PDF 文本若参与项目号识别等确定性规则，也需持久化为受控文本/对象引用，不能依赖旧进程中的 `ImagePayload.page_text`。渲染失败项不得生成虚假图片引用。

### 4.2 Stage 1：每页分类

复用 `PageClassificationResult`，另加类型化定位结构；分类、工作区映射和图纸投影分开，不把用户可修改的展示名称当主键。

```json
{
  "classification": {
    "run_id": "<run>", "project_id": "<project>", "profile": "<ProfileRef object>",
    "pdf_page_number": 3,
    "plant_function": "006C",
    "drawing_page_number": 1,
    "blank": false,
    "non_wiring": false,
    "confidence": 0.96,
    "needs_review": false,
    "reason": "<可见图纸证据>"
  },
  "page_identity": {
    "drawing_id": "<drawing-uuid>",
    "workspace_id": "<workspace-uuid>",
    "workspace_code": "006C",
    "workspace_name": "006C",
    "workspace_page": "1",
    "pdf_page_number": 3
  },
  "image_ref": "<typed private Storage reference>",
  "project_identity": {"project_no": null, "drawing_prefix": null}
}
```

说明：上述 `profile/image_ref` 的字符串仅表示复用类型，并非最终 JSON 值；实施时必须展开为对象。无法确认业务页号时 `workspace_page=null`，图纸身份使用物理页号，禁止猜测。当前阶段模型业务页号主要是整数，适配器向数据库文本 `workspace_page` 做明确转换；支持复杂文本页号属于另一次契约变更。

逐页上传归属工作区的图片副本后，把未发布项目树投影存入该 run 的分类 Artifact，**不逐页 upsert 共享 `workspaces/drawings`**。Stage 1 完成清单包含按物理页排序的页面引用、工作区分组和持久化图纸索引。封存/发布事务统一更新共享投影与项目发布指针，前端只展示发布快照（6.4）。下游以该 run 的分类快照为准，不直接消费另一个 run 的最新投影。

### 4.3 Stage 2：每页扫描

复用 `PageScanResult`，result 保存 `pdf_page_number/drawing_function/drawing_page_number/units/page_references/warnings/needs_review` 及固定的 run/project/profile 身份。

每个 unit 使用 `ScannedWireUnit`，每条连接使用 `ScannedConnection`。例如一个连接保存：

```json
{
  "connection_id": "<stable-stage-connection-id>",
  "unit_id": "<stable-stage-unit-id>",
  "origin_pdf_page": 3,
  "line_number": "<图纸原理号，无法识别则 null>",
  "start": {"device": "<起点代号>", "name": "<起点描述>", "terminal": "<起点端子>"},
  "end": null,
  "current": null,
  "remark": null,
  "color": null,
  "references": [],
  "is_cross_page": "unknown",
  "status": "needs_review",
  "source_pdf_pages": [3]
}
```

- `is_cross_page` 只保留现有三个值：`same_page/cross_page/unknown`，不加额外业务标志或跨页关系表。
- Stage 2 把已识别的端子排、起终点、电流、备注、色标和引用证据持久化；无法确认的字段为 null。
- 图纸原理号 `line_number` 与系统业务线号不同。中间 `wire_number` 不作为正式编号依据；最终 `wiring_units.wire_number` 仍由现有事务从 1000 分配。
- 每页原始扫描结果保持不可变。完成全部页后，用现有 Profile 策略确定性归一化/合并，生成独立扫描聚合快照；清单引用它，不能在 Build tasks 时原地改写 Stage 2 项。
- 稳定 stage unit/connection ID 与最终数据库 UUID 的映射由现有 Proposal builder/提交层完成；排序以来源物理页及页内视觉顺序为准，不以数据库返回顺序编号。

### 4.4 Build tasks：跨页任务

每个任务单独提交，`item_id=task:<task_id>`。任务结构由现有 `CrossPageTask` 升级为 Pydantic 模型，至少含：

- `task_id/unit_id/connection_id`；
- 来源 `source_drawing_id/source_pdf_page`、目标 `target_drawing_id/target_pdf_page`；
- 固定的 Stage 1 索引快照、Stage 2 连接 Artifact/聚合快照引用及 checksum；
- `references`、原始起点快照、允许补全字段；
- 解析结论：可处理或需复核，以及原因。

解析完全由 Profile 策略执行，不再靠 LLM随意选目标页。同一连接可对应多个目标页任务。目标不存在、外部资料缺失或 `unknown` 无可靠引用的项进入复核，不能靠常识补终点。`same_page` 且已完整的连接不调用 Stage 3。

### 4.5 Stage 3：每个跨页任务结果

复用 `CrossPageCompletionResult`，提交 `task_id/end/intermediate_points/current/current_basis/current_source_text/status/needs_review/confidence/source_note/warnings`，同时引用原任务项和来源/目标图片 checksum。

Stage 3 只能返回任务指定连接的补全数据，不能改起点、连接身份或整个 Stage 2 快照。聚合时校验 task_id，起点保持 Stage 2 原值；多个候选终点冲突则标复核，不以最后写入者覆盖。无跨页任务时，提交空结果清单并发阶段完成事件，不调用模型。

### 4.6 阶段完成清单和 checkpoint

每个阶段新增不可变 `StageSnapshotManifest` Artifact：

```json
{
  "schema_version": "1.0.0",
  "agent_run_id": "<run>",
  "stage": "PAGE_SCAN",
  "source_checksum": "sha256:<pdf>",
  "profile_checksum": "sha256:<profile>",
  "upstream_snapshot_ids": ["<stage1-snapshot>"],
  "expected_set_source_ref": "<sealed-upstream-or-frozen-input>",
  "expected_item_ids": ["pdf-page:1", "pdf-page:2", "pdf-page:3"],
  "item_refs": [
    {"item_id": "pdf-page:3", "artifact_id": "<scan-item>", "checksum": "sha256:<result>"}
  ],
  "aggregate_artifact_id": "<normalized-scan-snapshot>",
  "counts": {"expected": 3, "completed": 1, "skipped": 2, "failed": 0, "needs_review": 0},
  "ready_for_next_stage": true,
  "checksum": "sha256:<manifest-content>"
}
```

示例只展示一个 item_ref；真实清单必须覆盖所有权威预期项，跳过页也有引用。`expected_item_ids/counts/ready_for_next_stage` 为服务端计算的输出，不是提交者可以自行声明的完成依据。封存 RPC 必须从 6.2 指定的权威来源重建集合、检查无重复/遗漏/多余项；不得只比较客户端提交的列表和计数。清单 checksum 排除自身字段，引用按 item_id/物理页固定排序。

`agent_checkpoints` head（拟用 key `<run>:extraction:<stage>:manifest`）保存：

```json
{
  "schema_version": "1.0.0",
  "stage": "PAGE_SCAN",
  "snapshot_artifact_id": "<manifest>",
  "snapshot_checksum": "sha256:<digest>",
  "state": "committed"
}
```

逐项游标 key `<run>:extraction:<stage>:<item_id>` 指向成功项或最新失败尝试；完整历史留在不可变尝试 Artifact 中。checkpoint 顶层现有 revision 用于 CAS；清单不会把旧指针和新数据拼成一份结果。

V1 严格屏障：缺少项或 `failed>0` 不允许进入下一阶段，保留失败项供恢复。`completed` 但 `needs_review=true` 可继续，最终结果必须标复核；分类未知的页面可带显式未知身份处理，不能伪造业务页号。

### 4.7 最终业务字段对照与提交轮次

校验快照应包括稳定 unit/connection ID、完整来源和明确的 `normalized_rows`，转换沿用既有策略并逐字段回归：

| 用户字段 | 最终数据库字段/来源 | 阶段责任 |
| --- | --- | --- |
| 线号 | `wiring_units.wire_number` | 最终提交事务分配，1000 起；不是模型 `line_number` |
| 原理号 | `wiring_connections.principle_number` | Stage 2 的 `line_number`，校验后映射 |
| 电压等级 | `wiring_units.voltage_level` | 保留来源证据和确定性映射，不用常识猜测 |
| 端子排 | `wiring_units.terminal_strip` | Stage 2 端点/端子排信息，现有 Profile 策略归一化 |
| 起点代号/描述/端子 | `start_code/start_description/start_terminal` | Stage 2 的起点，Stage 3 不得改写 |
| 终点代号/描述/端子 | `end_code/end_description/end_terminal` | Stage 2 同页结果或 Stage 3 受控补全 |
| 电流/备注/色标 | `current_value/remark/color_mark` | 扫描及任务允许的补全，校验单位/来源 |
| 是否跨页 | `wiring_connections.is_cross_page` | Stage 2 三态，任务解析/校验保留证据 |
| 项目名称/工作区名称/工作区页码 | `projects.name/workspaces.name/drawings.workspace_page`，由视图关联 | 已登记项目与 Stage 1 分类定位；不在每条连接重复维护可改名字符串 |
| PDF 物理页号 | `drawings.pdf_page_number` + evidence | Render/Stage 1 固定身份，不能用业务页码替代 |

注意现有 `infrastructure/result_mapping.py` 的电压字段存在 `voltage_level → attribute → model` 回退。持久化迁移不能假设电缆型号天然等于电压等级；先原样记录源字段/证据并在字段级验收报告揭示该风险，如需纠正业务含义，另行确认映射契约、版本和回归，不在本轮方案中标为已解决。

Validation 轮次提交校验 snapshot（校验器 checksum、rows、warnings、needs_review、输入 manifest refs）；Proposal 轮次复用 `result_proposals` 保存现有 `ResultProposal`；最终提交轮次复用现有 result RPC，返回 `ResultCommitResult` 的版本 ID、版本号和 Proposal ID，再登记 result-version Artifact。完整提取保存 `draft/needs_review`，不会因为流程完成就伪标为用户已确认的 `accepted`。

结果提交与 run 完成必须按 6.3 收尾协议处理，不能因为 result-version Artifact 或事件写入失败，把已提交业务结果的 run 标为 `FAILED`。恢复先读取 receipt，不再次执行模型/生成新 Proposal/分配新版本。

### 4.8 输入摘要、业务结果摘要和完整记录摘要

以下 hash 均为 SHA-256；规范化规则版本 `canonical_json_v1` 随 Schema 固定：UTF-8、对象键排序、无额外空白、显式 null、不允许 NaN/Infinity、UTC 时间统一格式；数值规范化遵循字段类型，不擅自改写业务文本。只有 Schema 定义为集合的列表排序；连接视觉顺序、芯线次序、原始证据文本必须保留。

| 摘要 | 精确参与字段 | 明确排除字段 | 用途 |
| --- | --- | --- | --- |
| `input_fingerprint` | schema/canonicalization 版本、run/project/document/stage/item 身份、source checksum、冻结 Profile/Prompt/Few-shot/validator 版本或 checksum、按约定排序的上游 snapshot/item 引用及其业务摘要、图片/文本 checksum、模型名和生成/渲染配置、任务允许范围 | attempt、lease token、时间、metrics、error、输出 result | 匹配可复用的输入；模型名取调用前固定配置，实际返回模型不同需记录并校验 |
| `result_digest` | schema/canonicalization 版本、run/project/document/stage/item 身份、input_fingerprint、status（completed/skipped）、needs_review、整个类型化 result（含 warnings、confidence、来源证据、图像引用） | artifact_id、attempt、created_at、所有 metrics（含 model/duration/attempts/usage/cost）、error、raw_response_ref、摘要自身 | canonical 成功项去重；结果中的业务证据/页号不允许被排除 |
| `record_digest`（表顶层 checksum） | 不可变 Artifact 的完整业务记录：artifact_id/kind/run/stage/item、全部 envelope 字段及 result_digest、attempt、created_at、metrics、error、raw_response_ref | record_digest 自身、数据库系统字段/触发器时间、可变 head、lease 和 event seq | 存储完整性校验，不能用它判定重试是否为同一业务结果 |

`failed` 尝试不产生可消费的 result_digest；error/metrics/attempt 保存在 record_digest 保护的尝试记录内。manifest 的语义摘要包含权威集合来源、固定输入、完整排序 item_refs/result_digest、aggregate 引用、服务器计算 counts/ready；排除 checksum 自身和提交时间。引用字段在新契约中明确命名 `result_digest/record_digest`，本文示例的通用 `checksum` 在实施时按引用类型替换，禁止混用。

同一网络请求必须带固定 `commit_request_id`（首次生成后持久保存）与原 Artifact，不因 HTTP 重试新建 attempt。处理规则：

1. 同一 request ID、完整记录摘要相同：返回原 receipt，包括原 Artifact ID/checkpoint revision/event seq。
2. 同一 request ID、完整记录摘要不同：拒绝请求 ID 重用，不修改记录。
3. 新 attempt、相同 input/result_digest：canonical head 不变，返回原成功 receipt；新增尝试可用于消耗统计，不重复完成事件。
4. 新 attempt、相同 input、不同 result_digest：第一个成功事务选中 canonical，保存后来的冲突尝试/摘要，返回结构化 conflict；禁止覆盖、禁止“最后写入者获胜”。尚未封存时进入等待复核；已封存后原快照/下游输入不变，若要选择不同结果则显式创建新 run。
5. 已有 canonical 时正常恢复不得重新调用模型。超时后只重发提交；不能把模型再次生成不同结果当普通传输重试。

## 5. Storage 对象路径与本地缓存

沿用私有 `project-assets`；新增不可变内容路径，旧路径保留读取兼容：

```text
projects/{project}/original.pdf                                      # 当前一 PDF 一项目，保留
projects/{project}/runs/{run}/render/page-{physical}/{image_hash}.png
projects/{project}/workspaces/{workspace}/drawings/{drawing}/images/{image_hash}.png
projects/{project}/runs/{run}/{stage}/{item_hash}/{result_hash}.json  # 诊断副本，可选
projects/{project}/runs/{run}/exports/{result_version}/table.xlsx
```

stage 使用现有英文值规范化路径，如 `page-classification/page-scan/cross-page-completion`。业务名称、端子文本和任意本地路径不得直接拼对象键；用 UUID、物理页号和安全 hash 段。正文中路径皆为模板，不代表已经上传的对象。

分类前用 run-scoped 图片；分类后工作区目录中的 checksum 图片供项目树渲染。数据库 stage snapshot 保存确切图片引用，后续重提取不会覆盖旧 run 输入。原始 PDF checksum 改变时拒绝旧 run 续跑；V1 维持一 PDF 一项目，不顺手扩展多源文件模型。

本地 `.runtime/<run>/` 仅为缓存/诊断：下一阶段从数据库清单生成缓存，图片按 Storage 引用下载并验证 checksum，缓存缺失可重建。诊断导出失败只记告警；数据库或必需图片写入失败必须阻断阶段完成。

## 6. 提交协议、事务和故障恢复

### 单项提交

1. repository 校验 run 所属项目、固定输入、租约、取消状态及 Schema。
2. 如有必需图片/大对象，先上传不可变 Storage 对象并确认 checksum；Storage 与 PostgreSQL 不存在统一事务。
3. 调用受控 `commit_extraction_stage_item` RPC：在一个数据库事务内登记不可变项/尝试、更新 item checkpoint、按需写 Stage 1 投影及 `ITEM_COMPLETED`/失败事件。
4. 相同成功输入返回已保存 receipt；模型成功但数据库失败时重试提交缓存的结果，不立即再次调用模型。崩溃发生在落库前仍可能重算，不能声称模型调用 exactly-once。

### 阶段封存

1. 服务端从库加载各项，构建并校验 manifest；SQL 同时核对项存在、所属 run/stage、checksum、预期项和上游清单身份。
2. `commit_extraction_stage_manifest` RPC 原子保存 manifest、更新 checkpoint head 和阶段状态、写唯一 `STAGE_COMPLETED` 事件。Stage 1 全部投影完成才封存。
3. RPC 返回提交 receipt 后才进入下一节点；下一节点明确执行 `load_snapshot()`，不能直接传递刚计算的 Python result。
4. 提交成功但客户端超时可幂等重试，返回原 snapshot/event seq，不重复发事件；SSE 只能展示数据库中已提交事件。

不要由三个普通 repository 调用拼成“近似事务”。新 RPC 与现有事件序号分配机制复用同一锁顺序；停止依赖日志字符串推进业务状态。进度日志仍可展示，但不是提交凭据。

### 恢复/取消/并发

- 进程重启：从 run、阶段 manifest 和 item head 加载；已完成项跳过，仅重试未提交/失败项。清空本地缓存也必须可恢复。
- Stage 2 中途失败：保留 Stage 1 和成功扫描页；Stage 3 不启动。数据库提交冲突、Schema/权限/配置错误不盲目重试。
- Storage 成功、数据库失败：对象可能成为孤儿；不得发布完成事件。按 run 引用扫描、保留期和显式清理策略处理，不在异常路径随意删共享对象。
- 取消：模型批次边界检查；提交 RPC 也检查 run 未取消，避免取消后迟到结果发布完成。
- 现有租约默认 300 秒，长模型调用可能超过它。实施需补租约续期及 fencing 校验；item/manifest RPC 拒绝旧 lease owner/generation 提交，旧 Worker 也不能 acknowledge 新 Worker 租约。
- 用户新提取/修订建立新 run，保留原 Profile 版本与旧快照；本方案不把聊天短期记忆变成长任务事实来源。

## 7. 数据库 migration 与权限

不修改已应用 migration。建议新增文件名 `supabase/migrations/20261010000000_add_extraction_stage_commits.sql`，实施前核对时间戳是否占用；仓库目前迁移实际在 `supabase/migrations`，不为本任务搬到尚不存在的 `infra/supabase`。

该 migration 拟包含：

- 现有 `agent_artifacts` 新增 nullable stage、item_id、schema_version、input_fingerprint 等索引列；旧 Artifact 不强制回填，复合索引 `(agent_run_id, stage, item_id)`，唯一约束以 canonical item/manifest 的幂等键为准。
- 新 stage kind 的 CHECK/约束与内部 payload 身份检查；大集合分项提交、分页读取，不写整本 PDF Base64 或无界 checkpoint。
- 两个提交 RPC及租约续期/fencing 所需追加字段/函数；不新增跨页业务表，不改变现有最终结果表含义。
- stage RPC 为 service-role-only，固定 search_path，撤销 public/anon/authenticated 执行权；服务层按 run/project 关联校验，不能仅相信传入 project_id。
- 沿用现有表 RLS 的项目 owner/member 权限路径；验证匿名、非成员、成员读取与未授权写入。原始模型响应只通过受控授权接口暴露，避免把私有响应并入宽权限视图。
- 不可变 Artifact 无需 updated_at；可变 checkpoint 使用现有 updated_at/CAS。run 外键级联维持现有策略，不自动级联删除 Storage。
- 回滚仅关闭新入口/撤销新 RPC；有新数据时保留列与历史项，不用 DROP 清空产物。数据库/Storage 清理需显式目标及保留策略。

## 8. 文件改动清单

以下全部是拟改动路径（相对仓库根目录），不是本轮已实现内容。

| 文件/目录 | 改动 |
| --- | --- |
| `domain/models/stage_persistence.py`（新增，位于 `services/agent/src/agent_service/`） | envelope、manifest、输入引用、提交 receipt、类型化跨页任务/聚合快照 |
| `domain/models/extraction_stages.py` | 保持阶段结果兼容，补受控上下文引用与必要定位适配，避免端点/页号重复定义 |
| `domain/ports.py` | 新 `ExtractionStageRepository`：commit_item、commit_manifest、load_snapshot、list_items；类型签名不接受任意 SQL |
| `domain/schema.py`、`domain/models/__init__.py` | 注册新契约、版本/checksum 及导出；合同快照同步 |
| `infrastructure/stage_repository.py`（新增） | Memory/Fake adapter，与 Supabase 相同提交/恢复语义 |
| `infrastructure/supabase_stage_repository.py`（新增） | RPC adapter、分页/指纹加载、Schema 校验，不在 Graph 拼 SQL |
| `infrastructure/project_assets.py`、`storage_paths.py` | 逐页不可变图片写入、Storage 引用下载校验；Stage 1 项目树提交移入受控事务路径 |
| `infrastructure/supabase_repositories.py`、`infrastructure/queue.py` | 租约续期/fencing、CAS 整合与旧 runtime 兼容 |
| `application/stage_persistence.py`（新增） | 处理项提交、阶段封存、重建输入、错误分类和指标 |
| `application/extraction_run_executor.py` | 去掉 consume_progress 驱动落库；阶段 started/completed 由提交服务推进 |
| `application/three_stage_extraction.py` | 注入 Stage repository/context loader；生产入口只从持久化清单组装请求 |
| `application/document_extraction/runtime.py`、`ports.py` | 增加持久化依赖和图片缓存加载边界，不把领域层绑定 Supabase |
| `graphs/document_extraction/workflow.py`、`state.py` | 新 commit/load 节点；跨阶段 state 只保留 snapshot ID，DTO 明确 |
| `graphs/document_extraction/pages.py` | 分类/扫描循环逐项提交；恢复改为 repository，缓存 JSON 非权威 |
| `graphs/document_extraction/cross_page.py` | 任务生成/补全逐项提交；禁止原地改 Stage 2 数据，按清单重建 |
| `graphs/document_extraction/normalization.py`、`exports.py` | 聚合/校验快照，最终导出从持久化结果生成 |
| `application/worker.py`、`run_control.py` | 保留最终 Proposal/RPC；引用校验快照，取消/恢复与事件幂等整合 |
| `tools/result_proposal.py` | 从已提交校验结果重建 Proposal，保持现有最终字段映射 |
| `infrastructure/result_mapping.py`、`supabase_result_data.py` | 最终映射引用固定阶段身份/来源，避免被另一个 run 的最新图纸投影污染；既有字段含义变化另行评审 |
| `main.py` | 根据 persistence backend 注入正式 Stage repository |
| 新 migration（上一节） | stage 提交事务、查询索引、约束、权限及租约支持 |
| `tests/contract/test_domain_schema_snapshot.py` | 新 payload 与 checksum 契约 |
| `tests/unit/test_stage_persistence.py`（新增） | 类型/指纹/去重/空阶段/恢复策略 |
| `tests/integration/test_durable_extraction_stages.py`（新增） | Fake VLM + 全链路读写屏障、清空内存/缓存后续跑 |
| `tests/integration/test_extraction_worker_unittest.py` 等既有回归 | 新事件时序和最终结果兼容 |
| 新 Supabase 集成测试/冒烟脚本 | 真事务、并发、权限、租约、migration 双快照验证，显式执行 |

表中 `domain/…/main.py` 等未写根路径者均位于 `services/agent/src/agent_service/`；tests 位于 `services/agent/tests/`。Stage 1/2/3 子 Agent 的模型调用图优先保持现状，持久化放公共文档 Graph/application 层，不让 LLM 自由决定是否提交。

不重写 `profiles/zh` 的成熟识别规则，不修改 Profile Prompt/Few-shot；若实施中确需改输入契约则另作版本变更与固定回归，不能偷偷更换生产 Profile。原 CLI 通过注入 memory adapter继续使用，不伪称其具备 Supabase 持久化；正式 Worker 必须启用 database adapter。

## 9. 阶段 1 验收前置与脚本边界

当前阶段 0 会话附件只用于检测，不是业务 `document_files`。不能确认类型后直接把这个本地附件路径传入正式提取。

全链路验收另需服务端负责：项目/操作者登记、原 PDF 上传 Storage、source document 建立、冻结用户确认的 ProfileAssignment、创建有 base result version 的 FULL_EXTRACTION run、Worker 执行和 SSE 查询。该上传/确认衔接是后续单独的接口实现事项，不由阶段持久化 migration 隐式完成。

后续 `services/agent/agent_test/1.3stage/run_acceptance.py` 只发 HTTP 用户输入、上传、展示 SSE、查询阶段摘要；不能导入 Agent/tool/VLM/Supabase 或手动推进 stage。真实模型通过显式开关启用，报告模型、案例、各阶段耗时、费用（供应商不支持则 unknown）及字段差异，不能用 exit code 0 代替验收通过。

## 10. 分步实施与验收门槛

执行时按顺序，只允许一个步骤处于进行中；本轮只有方案编写完成，以下实现步骤全部未开始。

1. 契约与 migration：定义类型、repository、SQL/RLS/租约；空库和旧数据快照执行新迁移。
2. Render + Stage 1：逐页提交、项目树、清单屏障；删缓存后能从库恢复，Stage 2 不读旧状态。
3. Stage 2：逐页结果和聚合快照；任一数据库提交失败时 Stage 3 模型调用数必须为 0。
4. Build tasks + Stage 3：数据库清单驱动，起点锁定，无目标/冲突复核，空任务也可完成。
5. Validation + final commit：从数据库重建、最终业务 RPC、线号从 1000、结果幂等和版本冲突；取消及长任务租约验收。
6. 上传/确认衔接与纯 HTTP 验收脚本：真实 Supabase、显式真实 VLM，完成 `1.3stage/test.md` 链路。

必测场景：

- 每个阶段至少一次断电式进程中断；新 Worker、空本地缓存续跑，旧成功页/任务模型调用数不增加。
- 上传 Storage 后、DB commit 前/后分别故障；不能有虚假 completed、丢指针或重复 event。
- 同一输入重复提交、不同内容撞 ID、不同项目引用、两个 Worker 争同一项、租约到期迟到提交、取消后提交。
- 页面分类缺失、空白页、重复业务页号、业务页号未知、零连接、跨页目标缺失、多个候选终点、`unknown` 和全部 skipped。
- Stage 3 不改变 Stage 2 起点；跨页连接最终可追溯来源，物理页号不与业务页号混淆。
- 最终数据库字段级结果与现有固定回归一致；模型重试、费用、耗时不伪造。
- 空库/旧数据 migration、RLS 越权、签名 URL、分页加载、默认测试不调用付费模型。

完成定义：只有“阶段提交失败可阻断下游 + 丢失内存/缓存仍可续跑 + 最终规范化数据/事件一致 + 真实 HTTP 验收”全部通过，才标为阶段性持久化已实现。方案文件存在不等于这项能力已经完成。
