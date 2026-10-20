# Server 文档

- [主助手历史永久删除](./changelog/2026-10-19-assistant-conversation-deletion.md)、[设计](./assistant-conversation-deletion.md)：所有者删除、活动保护、级联元数据、持久附件清理及本地迁移/验收。

- [终点重扫目标绑定契约](./changelog/2026-10-19-rescan-target-contract.md)：API2.12.0/DTO/主助手传递，Worker按项目目录验证，无新迁移。

- [重扫规则独立固定](./changelog/2026-10-19-rescan-project-profile.md)：项目显式策略、入队版本快照和资源引用保护；新增迁移本地已部署。

- [指定项目规则引用替换](./changelog/2026-10-19-project-profile-rebind.md)：按用户要求改为ZH2.3.0，历史批次/局部重扫冻结版本保持；不自动重跑。

- [主助手历史当前执行状态](./changelog/2026-10-19-main-assistant-current-goal.md)：真实action状态/发布版本与范围标记，避免已发布候选被当成历史待办。

- [规则诊断失败闭环](./changelog/2026-10-19-main-assistant-tool-failure.md)：内部异常持久化failed并安全返回，业务工具失败不再重复至上限；需重载旧8000/8100。

- [范围检索与复合回执](./changelog/2026-10-19-main-assistant-progress.md)：精确编号集合/有界范围、指定行候选约束、版本2多任务回执及旧规则编辑继任。

- [主助手执行回执核验](./changelog/2026-10-19-main-assistant-receipt-guard.md)：答复发送前核对持久action和重扫任务，拒绝虚假编号/旧未核验重放，无新迁移。

- [主助手业务工具与确认交付](./changelog/2026-10-19-main-assistant.md)：API2.11.0、持久会话、受信工具、原候选确认与规则发布；新增迁移本地已应用，业务数据未变。

- [规则显示名称](./changelog/2026-10-19-profile-display-name.md)：所有者可按旧名称条件修改目录显示名，固定标识/ZIP/项目绑定，新增PATCH契约。

- [不完整样例发布契约](../agent/changelog/2026-10-19-permissive-publication.md)：ValidationIssue.severity和review_1.1.0同步，6项含实际打包/Mock发布的回归通过。

- [引导式规则配置契约](./changelog/2026-10-19-guided-profile-contract.md)：PDF任意阶段抽样、阶段来源和最多4张分类样图，需8000/8100同步加载。

- [规则会话删除API](./changelog/2026-10-19-profile-conversation-delete.md)：带修订/确认的DELETE、内部身份转发与204空响应。

- [数据库规则包目录](./changelog/2026-10-19-database-profile-catalog.md)：三套完整ZIP已发布，上传选项与Skills仅用数据库包，保留旧绑定；重载8000生效。

- [范围替换确认事务](./changelog/2026-10-19-rescan-scope-replacement.md)：21项隔离事务、部署能力保护及本地新迁移，API2.10.0。

- [项目XLSX导出](./changelog/2026-10-18-project-export.md)：当前正式批次全量13列、版本/权限核对、私有二进制响应，API2.9.0。

- [重扫附件与确认事务](./changelog/2026-10-18-explain-rescan.md)：私有图片、租约任务、候选CAS及数据/文件删除一致性，API2.8.0。

- [整组调换归属纠正](./explain-swap-origin-correction.md)：当前约定为所属页/工作区固定，坐标自带真实页号；新函数迁移和指定4行恢复已完成，取代此前迁页处理。

- [删除副本与修改后空表排障](./changelog/2026-10-18-explain-delete-relocation.md)：物理删除及副本清理、最小幂等回执、新迁移本地部署；调换后来源页筛选跟随，行ID不变。

- [Explain确认修改事务](./changelog/2026-10-18-explain-edit-transactions.md)：API2.7.0、proposal/RLS/版本/原子回执审计；本地仅部署新增结构，原三表不变。

- [规则编辑与新版替换](./changelog/2026-10-18-profile-editing-replacement.md)：API2.6.0、所有权/来源CAS、新版替换、项目/任务保护和持久回收；本地新迁移已部署。

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
