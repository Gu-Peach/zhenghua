# Explain 检索工具实施计划

依据：[ADR-0024](../../adr/0024-explain-retrieval-tools.md)。

1. 已完成：查询/分页/图纸契约、只读repository与工具；保留单行兼容。
2. 已完成：ModelGateway原生工具调用与分片、LangGraph条件循环、按需查看已检索图纸、会话刷新。
3. 已完成：51项Explain/共94项相关离线回归、13源码strict mypy/Ruff和CLI帮助通过；权限/分页/工具/图像摘要/SSE/OpenAPI及文档核对完成。旧Supervisor额外2项缺历史Prompt失败，未修改；未进行真实模型/数据库/前端联调。见[交付](./changelog/2026-10-16-explain-retrieval.md)。
