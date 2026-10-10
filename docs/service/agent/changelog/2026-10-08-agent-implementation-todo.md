# Agent 顺序开发与验收计划

日期：2026-10-08

## 变化

- 新增 `docs/service/agent/TODO.md`，作为 Agent 模块开发的执行清单。
- 将实现顺序固定为模块骨架、公共契约、Harness、Profile、提取子 Agent、纠错子 Agent和改进子 Agent。
- 为每个子 Agent 增加 Fake Model 测试、真实案例验收和退出条件。
- 将 M0“Agent 服务模块骨架”设为唯一进行中的 Agent 里程碑。

## 说明

本次仅更新计划和文档索引，尚未创建 `services/agent` 源码，也未将任何后续里程碑标记为完成。
