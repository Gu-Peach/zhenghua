# 电气图纸线表提取流程图生成 Prompt

## 主 Prompt

生成一张 **16:9 横向技术架构流程图**，主题为：

**电气原理图 PDF 线表提取方案（LangGraph Agent Pipeline）**

整体布局严格参考工程系统流程图：

- 白色或极浅灰背景；
- 顶部居中放置总标题；
- 左侧为窄列“主流程（LangGraph StateGraph）”，用纵向编号 1、2、3、4 展示四个核心节点；
- 中央为最大区域，横向展示四个处理阶段的详细子流程；
- 右侧为“结果存储（Supabase）”窄列，展示文件上传、数据库写入和前端读取；
- 所有模块使用清晰的细边框矩形，使用箭头连接，形成从 PDF 输入到前端结果的完整闭环；
- 内容以处理流程、Agent 调用、结构化结果和落盘文件为主，描述性文字尽量少；
- 不要生成营销页面、装饰性插画或复杂电气原理图，重点是可读的工程流程图。

## 画布结构

### 顶部标题

标题：

**电气原理图 PDF 线表提取方案（Agent 流程图）**

副标题可省略，不要添加大段说明。

### 左侧：主流程列

标题：

**主流程**

副标签：

**LangGraph StateGraph**

从上到下排列四个节点，每个节点使用独立颜色和编号：

1. **pdf_to_images**
   - PDF 页面渲染
   - 输出：页面 PNG

2. **segment**
   - 相邻页分段
   - 输出：segments

3. **extract_wiring**
   - 按段提取线表
   - 输出：records

4. **assemble_xlsx**
   - 归一化与校验
   - 输出：XLSX

节点之间用粗箭头垂直连接，明确表示执行顺序。

### 中央区域：四个处理阶段

中央区域按从上到下排列四个宽面板，分别使用低饱和蓝色、紫色、绿色、橙色区分。

---

#### 阶段 1：PDF 页面拆分 `pdf_to_images`

面板标题：

**1  PDF 页面渲染**

在面板内从左到右展示：

```text
PDF
  -> PyMuPDF
  -> page_001.png  page_002.png  ...  page_N.png
  -> pages 元数据
```

视觉元素：

- PDF 文件图标；
- 多张电气图纸缩略图；
- 小型页面元数据 JSON 卡片。

只显示以下短标签：

- `原始 PDF`
- `按页渲染`
- `PNG 页面`
- `page_number / image_path`
- `DPI >= 300`

输出箭头指向阶段 2。

---

#### 阶段 2：相邻页面分段 Agent `segment`

面板标题：

**2  相邻页面分段 Agent**

面板内从左到右展示：

```text
page_i + page_i+1
  -> Prompt S + 图片 few-shot
  -> VLM
  -> MergeDecision
  -> asyncio 并发 + 重试
  -> Union-Find
  -> segments
```

子模块依次包含：

1. **相邻页输入**
   - 两张原始页面图

2. **VLM 请求**
   - `Prompt S`
   - `few-shot 图片`
   - `Project.NR`
   - `drawing prefix`

3. **结构化判断**
   - `merge: true / false`
   - `confidence`
   - `needs_review`

4. **代码聚合**
   - `asyncio`
   - `retry`
   - `Union-Find`

输出卡片：

```text
merge_decisions.json
segments.json
```

在面板右侧增加一个很小的结果示意：

```text
(1,2) merge
(2,3) merge
(3,4) split
     -> [1,2,3] [4]
```

用两种箭头或颜色区分 `merge` 和 `split`。不要展示完整 Prompt、完整 JSON 或大段字段定义。

---

#### 阶段 3：线表提取 Agent `extract_wiring`

面板标题：

**3  线表提取 Agent**

面板内从左到右展示：

```text
segments
  -> 按段组织页面
  -> Prompt C + 图片 few-shot
  -> VLM
  -> JSON records
```

展示两个分支示意：

- 单页段：`[page_4] -> 1 张图`
- 多页段：`[page_1,page_2,page_3] -> 多图输入`

子模块标签只保留：

- `按段调用 VLM`
- `Prompt C`
- `真实图纸 few-shot`
- `跨页线号/端子延续`
- `JSON records`

结果卡片展示一个极简线表记录示意，只保留字段名：

```text
wire_number
start_terminal
end_terminal
terminal_strip
confidence
source_image
```

不要生成几十行表格，也不要生成密集的小字。

---

#### 阶段 4：结果校验与 XLSX 组装 `assemble_xlsx`

面板标题：

**4  结果校验与 XLSX 组装**

面板内从左到右展示：

```text
records
  -> Pydantic schema
  -> 端子格式归一化
  -> 端子排映射
  -> 一致性校验
  -> JSON / XLSX / 页面索引
```

核心处理标签：

- `JSON schema`
- `start_terminal / end_terminal`
- `terminal_strip mapping`
- `SPARE / PE`
- `低置信复核`
- `记录数校验`

输出使用三个文件图标并列展示：

- `records.json`
- `wiring-table.xlsx`
- `source-pages.json`

再连接到一个目录树卡片，展示：

```text
job_id/
  source/
  pages/
  groups/wire-table-001/
  agent/
```

---

### 右侧：Supabase 存储与前端读取

右侧标题：

**2.8  Supabase 存储方案**

从上到下绘制：

1. **后端上传**
   - `service-role key`
   - `images bucket`

2. **Storage 文件**
   - 原始 PDF
   - 页面 PNG
   - records JSON
   - wiring-table XLSX
   - agent diagnostics

3. **数据库写入**
   - `public.wiring_tables`
   - `job_id / group_id`
   - `pages / records / status`

4. **前端读取**
   - `Publishable / anon key`
   - `查询 wiring_tables`
   - `打开 PDF / 图片 / XLSX`

Storage 和数据库用两个不同图标表示，但都归属于 Supabase 区域。右侧用箭头表达：

```text
agent output
  -> images bucket
  -> public.wiring_tables
  -> 前端管理页
```

不要显示密钥内容、完整 SQL、完整 Storage 路径或权限策略。

## 底部信息条

在主流程下方放置四个横向小面板，作为结果和规则摘要，字体比主流程小一档但必须清晰。

### 输出结果

```text
records.json
wiring-table.xlsx
source-pages.json
merge_decisions.json
segments.json
```

### 线表关键字段

```text
wire_number | line_number | core_number
start_terminal | end_terminal | terminal_strip
confidence | source_image
```

### 端子规则

```text
起点：端子排:端子号
终点：保留图纸原写法
SPARE：*
PE：PE
```

### 可配置项

```text
VLM_MODEL
VLM_TIMEOUT_SECONDS
VLM_SEGMENT_CONCURRENCY
VLM_MAX_SEGMENT_PAGES
VLM_KEEP_TEMP_IMAGES
VLM_TERMINAL_STRIP_MAP
```

底部摘要只做辅助，不要抢过中央主流程的视觉权重。

## 视觉规范

- 专业工程软件架构图风格；
- 线性图标：PDF、图片、VLM、JSON、Excel、云存储、数据库；
- 颜色分区：蓝色代表页面处理，紫色代表分段 Agent，绿色代表线表提取，橙色代表结果组装，青色或蓝色代表 Supabase；
- 模块边框清晰，箭头方向统一，连接线不要交叉；
- 圆角矩形、轻微阴影、低饱和配色；
- 标题深蓝或深灰，流程节点文字高对比；
- 大量留白，严格对齐，网格化排版；
- 不使用渐变背景、发光球、复杂 3D、照片、人物或营销装饰；
- 不要把模块做成卡片套卡片，中央四个阶段使用平铺的宽面板；
- 所有文字必须清晰、无乱码、无错别字；
- 文字不可过密，优先保留节点名、输入、处理动作、输出文件。

## 负面 Prompt

不要生成：

- 海报、宣传页、网页 Dashboard、产品落地页；
- 复杂电气原理图细节；
- 大段解释文字、完整 Prompt、完整 JSON、完整 SQL；
- 密集表格、细小不可读文字、乱码、伪文字；
- 混乱的箭头、交叉连线、无方向流程；
- 与项目无关的服务器机房、人物、机器人、芯片或数据中心场景；
- 紫色渐变、发光球、玻璃拟态、过度装饰；
- 把 PDF、VLM、XLSX、Supabase 结果混成一个步骤；
- 遗漏 `pdf_to_images -> segment -> extract_wiring -> assemble_xlsx` 主链路。

## 推荐标题文字清单

如果图像模型对长中文支持较弱，优先保证以下文字准确，其余文字可以减少：

```text
电气原理图 PDF 线表提取方案
主流程
pdf_to_images
segment
extract_wiring
assemble_xlsx
PDF 页面渲染
相邻页面分段 Agent
线表提取 Agent
结果校验与 XLSX 组装
Supabase 存储方案
merge_decisions.json
segments.json
records.json
wiring-table.xlsx
public.wiring_tables
前端管理页
```
