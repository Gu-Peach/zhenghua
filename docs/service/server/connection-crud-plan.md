# 单条端子增删实施计划

用户已明确需要单条端子新增/删除，并允许创建、清理一次性验收数据。不增加表、列或 SQL 函数，不修改 Agent 核心和 test0。

1. 已完成：Server PostgreSQL 事务复用既有表。项目/结果行锁、owner/editor 授权、revision/record_version、幂等 receipt、完整 before/after。新增归入已有线号；删除指定连接并先归档证据；保留空单元、其他 ID/排序/线号及结果代次，按待复核状态更新结果状态。
2. 已完成：HTTP/Pydantic/OpenAPI 与 Web 新增/删除确认；新增指定所属线号和来源页，跨页明确目标，不猜引用。无事务配置返回 503，未确认删除返回 422。
3. 已完成：24 项默认 API、5 项 HTTP 浏览器夹具回归；一次性真实 Auth/DB/Storage/API 和浏览器增改删、双图预览通过。验证越权/过期/幂等冲突与重放/注入审计失败全量回滚；临时项目、对象、账号及自建进程均清理，test0 未改。

单条 CRUD 已交付，不等于 PDF/Agent 全链路已验收。完整提取 Fake 测试在共享队列 Worker claim 处失败，有其他活跃消费者；未声明通过，未停止用户服务。

事务连接用 SERVER_DATABASE_URL，仅 Server 持有。REST service-role 不能组合成数据库事务，因此不能用多个无事务 PATCH/DELETE 模拟原子提交。无配置时返回明确 503，不绕过版本/审计。既有编辑 RPC 保持不变。
