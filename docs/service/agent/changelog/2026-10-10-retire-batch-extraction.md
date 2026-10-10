# 删除旧相邻页分段和批量提取

日期：2026-10-10。决策：[ADR-0005](../../../adr/0005-retire-zh-workflow-runtime.md)。

用户明确不再需要旧相邻页分段和批量提取。删除 `application/document_extraction/legacy.py`、`segment_decider.py` 与旧 segment-decider import 入口。同步清理批量 client、batch planner、批量 checkpoint、批次结果合并、旧 XLSX 节点及仅被它们调用的辅助函数。

Runtime/Graph 不再保存或接收 segment-decider/prompt，Profile adapter 继续读取真实三阶段 Prompt。旧分段并发与页数设置移除，旧环境变量被忽略，不影响其余 `VLM_*` 兼容配置。新运行不再输出 `merge_decisions.json` 和 `extraction_batches.json`；页面分类/页扫描/跨页 checkpoint、来源证据、ResultProposal、11 列诊断 XLSX 与数据库契约保持原用途。独立的标准/模板导出工具仍保留。

Agent HTTP/Worker 与测试 CLI 的调用路径是 `three_stage_extraction -> graphs/document_extraction/workflow`。旧 `zh_workflow` 目录只用于转发当前功能的旧 import，未保存旧运行算法。新增测试确认旧 batch 模块不存在、兼容模块不再暴露旧节点，且保留的旧 graph 名称与新 graph 指向同一函数。

默认 Agent 测试 93 项通过；全包 161 个源码文件 strict mypy、Ruff 与编译检查通过。未调用真实 VLM，未重启已有测试进程，也未删除历史任务产物或修改旧 backend。
