# Server 文档

- [Profile发布“数据操作失败”与迁移补齐](./changelog/2026-10-17-profile-publication-missing-migration.md)：本地发布RPC已部署、包摘要与权限核对通过，用户重试发布；缺接口返回安全配置错误。

- [Profile PDF抽样代理](./changelog/2026-10-17-profile-pdf-sampling.md)：API2.5.0、鉴权/幂等/来源恢复契约，无新增业务表或迁移。

- [Profile对话鉴权代理](./changelog/2026-10-17-profile-conversation.md)：API2.4.0、新对话GET/SSE、生成契约及权限/恢复验证，无新迁移。

- [规则草稿创建404排查](./changelog/2026-10-17-profile-draft-404.md)：运行8000仍为2.2.0、未加载新增路由，需用户重载到源码2.3.0；3项离线链路测试通过。

- [Profile三步创建代理与手动发布](./changelog/2026-10-17-profile-publication.md)：API2.3.0、私有固定版本包、可信发布RPC及目录/Worker加载；首次交付未部署，本地迁移现已补齐，其他环境需单独部署。

- [Explain鉴权代理与生成契约](./changelog/2026-10-17-explain-proxy.md)：API 2.2.0、只读JWT/项目边界和共享8100代理，未重启实际服务。

- [上传入队、鉴权SSE、增量事务及隔离库验证](./changelog/2026-10-16-incremental-extraction.md)。

- [起终点坐标字段及验证](./changelog/2026-10-16-terminal-coordinates.md)、[坐标契约](./terminal-coordinate-contract.md)

- [2026-10-16 三表数据管理接入与验证](./changelog/2026-10-16-simple-management.md)、[ADR-0020](../../adr/0020-three-table-management-contract.md)

- [本地旧业务表删除与三表实际部署](./changelog/2026-10-14-local-business-table-retirement.md)

- [三张精简业务表创建SQL及接入限制](./changelog/2026-10-14-simple-extraction-schema-sql.md)

- [规则包新建、删除与自动注册计划](./rule-package-lifecycle-plan.md)
- [规则包生命周期实施记录](./changelog/2026-10-12-rule-package-lifecycle.md)
- [工作台接入计划](./workbench-integration-plan.md)
- [2026-10-12 实施进度](./changelog/2026-10-12-real-workbench.md)
- [真实模型联调与续跑状态](./changelog/2026-10-12-live-agent-acceptance.md)
- [完成性核对与待确认边界](./workbench-completion-audit.md)
- [运行说明](../../../services/server/README.md)
