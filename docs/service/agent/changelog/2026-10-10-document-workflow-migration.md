# 文档工作流与 ZH 策略迁移

日期：2026-10-10。关联决策：[ADR-0005](../../../adr/0005-retire-zh-workflow-runtime.md)。

## 实现

- 正式入口 `application/three_stage_extraction.py` 调用 `graphs/document_extraction/workflow.py`，三个专业 Agent 子图及模型 Gateway 保持原调用关系。
- 原 2600 余行工作流拆成 workflow、pages、cross_page、normalization、exports、helpers、state；checkpoint 独立迁入 infrastructure/document。
- `domain/models/wiring.py` 保存扁平结果；结构化 Unit/Connection/Endpoint 等复用 `extraction_stages`。旧 checkpoint 辅助身份/引用字段在转换边界分离，保留严格模型契约。
- PDF、图片归类移动、Few-shot 读取、JSON 响应解析、标准和模板 XLS/XLSX 分属基础设施。归类图片文件移动通过线程执行，恢复复用原图路径，冲突业务页保持不同物理页。
- `profiles/zh` 拥有端子白名单、终端归一化、方向、电流来源校验、EPLAN 引用、跨页合并和导出字段；公共 Graph 只调用 `ExtractionPolicy`，writer 通过 `ExportFields` 注入模板映射。
- `zh_workflow` 保留薄旧 import 兼容入口；正式源码不依赖旧包。迁移时暂留的旧批量/相邻页 compatibility helpers 随后按用户要求删除，见[删除记录](./2026-10-10-retire-batch-extraction.md)；正式 Graph 统一使用三个阶段。
- 数据库 migration、Prompt、Few-shot 图片与 Profile resource checksum 未变。CLI 命令和 HTTP/Worker 入口保持原用法。

## 验证

- 迁移前默认 Agent 测试 86 项通过。
- 迁移后默认 Agent 测试 91 项全部通过。
- 新增两页非空 PDF 回归：允许起点、反向连接、拒绝连接、跨页单目标、电流来源、来源页、字段级 JSON/XLSX 对照及恢复不重复调用模型。
- 新增生产 import 边界、未注册 adapter 拒绝、共享 domain 模型及兼容导出映射检查。
- 全包 166 个源码文件 strict mypy、Ruff 与 compileall 通过；第三方 PDF/Excel 无类型存根仅在对应边界处理。
- 真实 Supabase 全工作流通过：提取版本 1、确认修订版本 2、线号 1000、accepted feedback、候选 ACTIVE、评测持久化与权限验证；未调用 VLM。

真实 VLM 字段级基线、进程被终止后的完整恢复以及 ABB 独立资产回归仍属于后续验收；本次恢复验证为重建文档运行上下文并读取已落盘 checkpoint。
