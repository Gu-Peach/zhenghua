# ADR-0011：人工端子增删使用既有表的原子事务

状态：accepted（用户于 2026-10-12 明确需要单条端子新增/删除）。

## 决策

既有 apply_confirmed_result_patch 仅支持 replace，不修改已应用 migration，不新增 SQL 函数，不克隆结果集合。Server 用只持有服务端的 PostgreSQL 连接进行参数化事务，在项目/最新结果行锁下执行人工 add/remove。

新增：归入已有 wiring_unit（线号不变），明确来源图纸；数据库分配新的连接 UUID/core_order，记录人工来源证据；跨页必须明确目标页或标 unknown，不猜引用。删除：先保存完整连接及证据到 feedback before JSON，再仅删除指定 connection；证据由既有外键级联，其他 ID/线号/core_order 不改。删除最后一条连接仍保留空单元，供后续新增，不释放或重排线号。

每次操作创建手工审计 run/proposal/accepted feedback，记录操作者/时间/来源页/输入摘要/幂等 receipt，result revision 原子递增。调用者必须 owner/editor，并确认当前结果代次/revision；删除还校验 record_version。丢失响应重试返回原 receipt，不重复插入/删除。不同内容复用 key 拒绝。连接信息只在 Server 配置，不下发浏览器。

## 边界

不改 Agent 核心；既有编辑 RPC 保留。无 SERVER_DATABASE_URL 时明确返回 503，不能以分散 REST 写入冒充事务。默认不调用模型；真实验证只使用用户允许的一次性项目/账号，清理后不保留业务测试数据，不动 test0。
