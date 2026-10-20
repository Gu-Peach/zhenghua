# 主助手答复在执行回执核验后发送

为防止“会话回复完成”被误当成“重扫已创建”，新增 `assistant_completion.py`，由 `assistant_service.py` 在发送最终答复前核验业务事实。

- 暂存answer_delta，只有completed带有效核验元数据且所需业务action存在时才发送并保存答复。核验失败时丢弃未验证文本，本轮保存failed和安全错误，不保存虚假成功答复。
- task_started与重扫完成确认校验action的所有者、会话、轮次、工具名，以及关联任务的run ID、项目、创建者和会话。跨用户、跨会话、跨轮次、错run ID或任务不存在均拒绝。
- 重扫答复由Server根据查询到的真实run ID和最新状态重新构造；即使上游文字夹带另一个编号，也不能作为启动回执显示。
- 查询歧义的clarification必须对应真实find_targets回执。普通问候/知识答复可以以answered结束，不会创建任务。
- 旧版completed没有核验元数据时不再直接重放为成功；提示重新发送需求，不重写历史业务数据或自动重扫。

沿用AssistantEvent.data扩展元数据，无新API DTO/表/迁移。已在内存中比对OpenAPI与现有文件完全一致，TypeScript契约无需改变。需8000/8100一起重载，旧8100不能绕过新Server校验。

本次分批验证：14项Agent和82项Server测试通过，46个显式集成测试保持跳过；包括贯通模拟中“模型编造编号→补调真实Facade→持久任务回执→正确SSE→同轮重放不重复入队”。8项主助手浏览器回归通过，Ruff、Agent/Server mypy及差异检查通过。没有调用真实模型、创建实际重扫、改实际线表或启停用户进程。
