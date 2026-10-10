# 三阶段持久化方案记录

日期：2026-10-10。仅文档交付，代码/数据库尚未实施。

用户确认阶段 0 测试通过后，要求在 `1.3stage` 验收前先设计“每阶段处理完持久化，下一阶段从库查询”的链路。已根据现有 Graph、阶段模型、repository、Storage 路径及已存在 migration 编写 [改造方案](../stage-persistence-refactor-plan.md) 和 proposed [ADR-0007](../../../adr/0007-durable-extraction-stage-boundaries.md)。

方案覆盖逐页/逐任务结构化数据、不可变阶段清单、checkpoint head、受控事务提交、私有 Storage 与可重建缓存、事件时序、租约/取消/恢复、最终业务字段以及拟改动文件。不增加三张阶段业务表，不改变 `is_cross_page` 三态，不把中间提取结果冒充最终线表。

已同步 Agent 索引、重构方案、roadmap 和 TODO；检查文档链接及变更格式。本轮未运行模型、未应用 migration、未修改 Python/SQL、未启动或停止服务。下一步是方案评审后按依赖顺序实施，不将方案编写标记为生产能力完成。
