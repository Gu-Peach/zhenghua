# 删除 zh_workflow 兼容目录

日期：2026-10-10。决策：[ADR-0005](../../../adr/0005-retire-zh-workflow-runtime.md)。

仓库范围确认生产源码和脚本均已直接依赖新模块，旧路径仅用于兼容测试。因此删除整个 `services/agent/src/agent_service/zh_workflow` 目录，包括 16 个兼容 Python 文件及该目录的本地字节码缓存。

旧 schema/导出/Graph 别名测试改为检查共享 domain、注入的 ZH 导出字段、旧 batch 模块不可用以及兼容包不存在。正式提取仍从 `three_stage_extraction` 调用 `graphs/document_extraction/workflow`，CLI 与 HTTP/Worker 入口无需改名。`agent_service.zh_workflow.*` import 不再受支持。

数据库、Prompt、Few-shot 和历史运行产物未修改；验证使用默认 Fake 模型测试，不调用真实 VLM，也不重启已有测试进程。

验收：93 项默认 Agent 测试全部通过，全包 145 个源码文件 strict mypy、Ruff 和 compileall 通过；目录不存在、旧包不可导入检查通过。
