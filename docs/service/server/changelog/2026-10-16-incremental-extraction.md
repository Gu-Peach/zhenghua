# 三表增量提取接入

上传保存成功后调用`start_simple_extraction`，以稳定run ID入队。重复上传同一幂等键不重复创建任务；上传失败不入队。浏览器不持有service-role，也不直连Agent执行提取。

新增接口：

- `GET /projects/{id}/extraction`：阶段、页计数、行数和安全错误。
- `GET /projects/{id}/extraction/events?cursor=...`：JWT鉴权SSE，通知客户端补读业务快照；55秒后重连并重新验证会话。持续核对项目所有者，授权失败终止流。
- `POST /projects/{id}/extraction/retry`：失败任务显式重试，保留原批次与已完成缓存；运行或完成任务不会重复入队。

路径均以`/api/v1`为前缀。项目详情增加processing，行DTO增加processing_status和review_reasons；OpenAPI与TS已同步。提取中结果只读，API及事务RPC都阻止人工编辑；提取完成/失败后恢复数据管理操作。

迁移`20261016020000_incremental_extraction.sql`新增领取、续租、启动及事务发布RPC、领取/活动任务唯一索引，并兼容旧gate_a触发器对已删除projects表的引用。新旧Worker队列隔离，原协议2 fencing保留。所有新RPC仅service_role执行，事务校验所有者、归档、租约、物理页范围和人工版本。发布原子包含行、索引、计数、产物和事件；写库成功后前端才收到通知。页面复核也影响run最终状态。

私有project-assets允许application/zip，用于冻结规则包；不改变私有状态或原有MIME能力。

新资产使用`projects/<project>/runs/<run>/...`。确认删除项目会清理页面和冻结规则包，包括已上传但尚未成功发布索引的图片；处理中的项目继续禁止删除。失败数据保留。

验证：19项API夹具测试；`verify_incremental_migration.py --allow-local-database-test`在固定本地容器的两个一次性数据库中，分别验证空表及带旧批次数据的迁移、私有ZIP能力、并发重复入队、索引更新、租约互斥、同一行更新、重复提交、人工版本保护、失败恢复、终态重放、页级review和RPC权限。临时库自动移除，当前项目库未部署该迁移。没有调用模型；未做真实网络/付费模型的端到端性能或精度验收。

上线顺序：迁移 → 新Worker与8000 API → 前端。回滚应先停新Worker，新增迁移恢复旧guard/CRUD定义、移除新增函数和索引，按需要撤回ZIP上传类型；保留业务数据。


## 后续启动排障

用户启动Worker时`claim_simple_extraction`返回404。只读核对发现本地迁移历史止于20261016010000，新增RPC不存在。已仅部署20261016020000至固定的supabase_db_zhenghua_test/postgres，并在同一事务登记schema_migrations；未批量执行其他待应用迁移。部署前函数及桶配置保存在被忽略的.runtime/migrations/20261016020000-before.sql。

只读HTTP验证四个提取RPC已在PostgREST OpenAPI可见，8000 API版本为2.1.0；未领取任务、未上传测试数据、未调用模型或重启服务。用户重跑原Worker命令即可。原交付段落的“未部署”描述为此前状态。
