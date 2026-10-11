# 三阶段持久化方案记录

日期：2026-10-10。仅文档交付，代码/数据库尚未实施。

用户确认阶段 0 测试通过后，要求在 `1.3stage` 验收前先设计“每阶段处理完持久化，下一阶段从库查询”的链路。已根据现有 Graph、阶段模型、repository、Storage 路径及已存在 migration 编写 [改造方案](../stage-persistence-refactor-plan.md) 和 proposed [ADR-0007](../../../adr/0007-durable-extraction-stage-boundaries.md)。

方案覆盖逐页/逐任务结构化数据、不可变阶段清单、checkpoint head、受控事务提交、私有 Storage 与可重建缓存、事件时序、租约/取消/恢复、最终业务字段以及拟改动文件。不增加三张阶段业务表，不改变 `is_cross_page` 三态，不把中间提取结果冒充最终线表。

已同步 Agent 索引、重构方案、roadmap 和 TODO；检查文档链接及变更格式。本轮未运行模型、未应用 migration、未修改 Python/SQL、未启动或停止服务。下一步是方案评审后按依赖顺序实施，不将方案编写标记为生产能力完成。

## V1.1：六项一致性评审补充

补齐过期 RUNNING 原子接管、所有 Worker mutation 的 fencing/旧入口隔离、暂时失败退避；预期项由 PDF 页数/上游清单/连接 planning coverage 推导并由 SQL 校验，counts/ready 不开放给调用方；结果落库后 durable receipt 驱动幂等 finalize，失败/取消不能覆盖已提交结果；逐页分类仅存未发布 Artifact，Stage 1 封存后以项目 epoch 和 snapshot 指针原子发布；细分输入/业务结果/完整记录摘要，规定 request ID 重用和相同输入不同输出的冲突策略；拆分 Gate A（真实 DB + Fake VLM）与 Gate B（HTTP 用户链路/真实模型）。

方案第 11 节给出评审闭环对照表。此次只复核源码/既有 SQL 并修订文档，未运行测试或查询线上数据库；文档链接和格式单独检查。架构和顺序保留，代码/migration 仍未开始。
