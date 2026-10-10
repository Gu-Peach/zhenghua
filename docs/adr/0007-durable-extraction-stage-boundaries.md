# ADR-0007：三阶段提取的数据库持久化边界

日期：2026-10-10。状态：proposed（待评审，未实施）。

## 背景

目前三阶段通过 GraphState 与本地 checkpoint 串联，Supabase 阶段产物上传由异步进度队列推进，不是下一阶段启动的必经屏障。用户要求阶段处理完先持久化，下一阶段从数据库查询后再处理。

## 拟定决策

1. 复用 `agent_artifacts` 存类型化、不可变逐项结果和阶段清单；`agent_checkpoints` 存可变 head/CAS；不为 Stage 1/2/3 各建一张业务表，也不增加跨页关系表。
2. Stage 1/2 按物理页、Stage 3 按跨页任务立即提交；全阶段封存后下一阶段重新加载数据库清单，内存和本地 JSON 只作缓存。
3. 采用追加 migration、service-role-only RPC，把 Artifact、checkpoint、必要项目树投影及完成事件置于同一 PostgreSQL 事务。Storage 先上传不可变对象，再提交其引用；失败孤儿按保留策略清理。
4. `is_cross_page` 保持 `same_page/cross_page/unknown`；Stage 3 只补任务指定连接，不改已确认起点。
5. 中间结果不是正式线表。最终仍由校验、Proposal 和现有受控事务创建结果版本，数据库分配 1000 起业务线号。
6. 冻结输入/Profile，补 CAS、租约续期和 fencing，保证取消/崩溃/新 Worker 恢复时不会接受过期 Worker 的迟到提交。

## 权衡与边界

数据库读写次数增加，换取阶段独立恢复、可审计输入和严格完成语义；JSONB 内部阶段项复用现有运行时表，最终业务字段保持可查询列。大图片在 Storage；大型清单分页/分片，不把整本结果塞入 checkpoint。

不重写成熟 Profile 算法，不启用长期聊天记忆，不迁移旧数据库历史，不在方案阶段应用 SQL 或启动真实模型。阶段 0 私有会话附件到业务项目的衔接另需服务端接口，不能由客户端编排工具代替。

详细 payload、位置、改动文件、实施顺序和验收见 [三阶段持久化改造方案](../service/agent/stage-persistence-refactor-plan.md)。
