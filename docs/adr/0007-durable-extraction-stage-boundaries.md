# ADR-0007：三阶段提取的数据库持久化边界

日期：2026-10-10。修订：V1.1（六项一致性评审补充）。状态：accepted（用户授权实施 Gate A，机制已验证；Gate B 未实施）。

## 背景

目前三阶段通过 GraphState 与本地 checkpoint 串联，Supabase 阶段产物上传由异步进度队列推进，不是下一阶段启动的必经屏障。用户要求阶段处理完先持久化，下一阶段从数据库查询后再处理。

## 拟定决策

1. 复用 `agent_artifacts` 存类型化、不可变逐项结果和阶段清单；`agent_checkpoints` 存可变 head/CAS；不为 Stage 1/2/3 各建一张业务表，也不增加跨页关系表。
2. Stage 1/2 按物理页、Stage 3 按跨页任务立即提交；全阶段封存后下一阶段重新加载数据库清单，内存和本地 JSON 只作缓存。
3. 采用追加 migration、service-role-only RPC，把 Artifact、checkpoint 和完成事件置于同一 PostgreSQL 事务。逐页分类投影仅在 run Artifact 中未发布保存；Stage 1 封存后原子发布业务项目树与指针。Storage 先上传不可变对象，再提交其引用；失败孤儿按保留策略清理。
4. `is_cross_page` 保持 `same_page/cross_page/unknown`；Stage 3 只补任务指定连接，不改已确认起点。
5. 中间结果不是正式线表。最终仍由校验、Proposal 和现有受控事务创建结果版本，数据库分配 1000 起业务线号。
6. 冻结输入/Profile，补 CAS、租约续期和 fencing。原子接管过期租约的 RUNNING run；所有 Worker 写状态/事件/Proposal/最终结果/finalize/ack 路径均验证 owner/generation/expiry，旧非 fenced 入口不能写新协议 run。
7. 预期页来自服务端冻结 PDF 页数，Stage 1/2 来自上游完整页集，Stage 3 来自封存任务清单；Build tasks 对全部扫描连接保存 planning decision。SQL 重算 counts/ready 并验证集合相等，客户端不可自报完成。
8. 保留现有最终结果算法，添加 fenced result wrapper 及 durable receipt；结果已提交后只恢复收尾，不重跑模型/新建版本。finalize 原子登记 Artifact、run 终态和唯一完成事件；已提交结果不得被失败/取消处理覆盖。
9. 项目发布 epoch 与 published 分类 snapshot 指针控制树展示；旧 run 封存自己的快照不能覆盖最新授权 run 的项目树。封存前初次项目仅见 PDF，重提取期间保留旧已发布树。
10. 区分 input_fingerprint、result_digest、record_digest；attempt/metrics/error 排除于业务结果摘要而纳入完整记录摘要。相同输入不同结果保留冲突，first-success canonical 不覆盖。
11. Gate A 为真实数据库+Fake VLM 的机制验收；Gate B 为上传/确认/HTTP/SSE及显式真实模型的用户链路验收，两者分别标记完成状态。

## 权衡与边界

实施补充：新协议工作区/图纸的物理 UUID 绑定 run 分类快照，项目树按 published pointer 查询，最终线表按本 run 快照映射。保留旧投影，避免新分类覆盖旧结果证据；不新增三张阶段表。租约永久失效用 PT409，不伪装为可重试序列化故障。实际提交与验证见 [实施记录](../service/agent/changelog/2026-10-10-gate-a-implementation.md)。

数据库读写次数增加，换取阶段独立恢复、可审计输入和严格完成语义；JSONB 内部阶段项复用现有运行时表，最终业务字段保持可查询列。大图片在 Storage；大型清单分页/分片，不把整本结果塞入 checkpoint。

不重写成熟 Profile 算法，不启用长期聊天记忆，不迁移旧数据库历史，不在方案阶段应用 SQL 或启动真实模型。阶段 0 私有会话附件到业务项目的衔接另需服务端接口，不能由客户端编排工具代替。

详细 payload、位置、改动文件、实施顺序和验收见 [三阶段持久化改造方案](../service/agent/stage-persistence-refactor-plan.md)。
