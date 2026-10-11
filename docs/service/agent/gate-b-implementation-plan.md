# Gate B 执行计划

日期：2026-10-11。Gate A 保持原样；本次不建设 Web 或 apps/api JWT 代理。

## 接口及一致性边界

内部 Bearer 保护的业务上传接口接受 PDF、已有 Supabase Auth 用户 UUID、项目名、conversation_id 和 Idempotency-Key。服务端检查真实 PDF/页数，按用户+key 固定项目/文档 UUID，数据库先保留 checksum 再上传不可变私有对象，重复请求校验内容，失败可重试；不创建用户，不覆盖不同内容。阶段 0 附件接口继续只检测。

Supervisor PROCESS_DOCUMENT 检测首页并强制人工确认，确认后服务端创建带冻结 Profile 版本、确认者、源 checksum、base version 的 FULL_EXTRACTION protocol 2 run。确认与入队按业务固定 key 幂等；未确认不启动三阶段，experimental Profile 不可用于正式提取。会话记忆仅短期；已创建任务和结果从数据库查询，API 请求不承担长提取。

补内部项目树/结果和 run 阶段摘要查询。树只显示 published snapshot；结果按固定版本分页；SSE 支持 Last-Event-ID，终态前排空所有已持久事件。客户端只上传、发送自然语言、终端确认、展示/查询，不编排工具，不连接数据库。

## 顺序

1. 完成：上传/查询 adapter、类型契约、确认到持久 run 的应用服务。
2. 完成：内部 HTTP 路由、SSE 和纯 HTTP 终端脚本。
3. 完成：默认 Fake HTTP 回归、显式本地 Supabase/Fake 模型链路验证、文档与类型检查。
4. 待开始：显式真实模型人工案例验收（模型费用/耗时/字段差异记录；未运行保持未验收）。

无需三阶段新表；优先复用 Gate A migration，不改已应用 SQL。若发现必须改变数据库协议，先在隔离数据库验证再追加 migration。

已新增一份 `20261011000000_atomic_business_extraction_creation.sql`（仅事务函数/权限），在隔离空库/旧数据及故障回滚验证后应用本地库。真实模型步骤 4 未执行，需要操作者提供已有 Auth UUID 和人工 PDF baseline；不能称整个 Gate B 准确率验收通过。
