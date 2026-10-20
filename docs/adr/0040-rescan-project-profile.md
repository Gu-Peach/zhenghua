# ADR 0040：重扫使用项目当前选定规则

状态：代码/离线与隔离SQL验收、本地迁移和指定项目策略启用完成。用户已明确要求指定STS项目的重新扫描使用最新2.3.0，前一轮已将该项目profile_id改为数据库zh2.3.0。实际Worker仍需用户重载后新建任务。

不覆盖旧批次的profile-package或修改旧任务快照。新增项目级显式策略drawing_index.rescan_profile_source=project_reference：仅启用项目的新入队任务，按项目当前profile_id选已发布Storage规则，冻结key/version/checksum、profile_ref和来源标记到job快照。没有策略标记的项目与旧任务继续使用历史规则。所谓最新在此指用户为项目选定的已发布版本；Worker不能运行中追随目录最新版本。

Worker对project_reference来源只读取job冻结的ZIP引用，校验归档摘要及包内身份，禁止回退批次包或本地规则；老任务保持原冻结路径。持久化RescanSnapshot模型必须保留来源字段，断点配置升级隔离旧代码缓存。新版本资源只要被重扫job引用便不能GC，原规则/其他项目不动。

新增migration替换入队函数并加强profile_version_in_use，不修改已应用迁移。既有鉴权、批次/范围/附件、幂等及确认事务保持。新候选引用本次job规则，原行before证据保留，确认前不修改线表。切换策略不自动创建任务或重跑模型。需要用户加载Worker新代码后再发起新一轮。

验收：先补Fake包加载与SQL入队失败回归；核对新任务用项目2.3.0而非baseline2.2.1、旧任务幂等不变、摘要/身份/来源不合法拒绝、项目越权拒绝、资源在用保护；空库与含旧任务快照隔离库迁移，最后本地只部署Schema与指定项目策略，核对旧包/任务/线表不变。

交付：[Agent](../service/agent/changelog/2026-10-19-rescan-project-profile.md)、[Server](../service/server/changelog/2026-10-19-rescan-project-profile.md)。173项默认测试及16项隔离SQL分批通过，50项显式集成默认跳过；Ruff/mypy和公开OpenAPI一致性通过。未调用真实模型、发布规则或提交线表。回滚先关闭项目策略并停止新入队，保留已创建任务及其资源，由支持来源标记的Worker完成/取消；恢复入队函数可用部署前Schema备份，GC引用保护可保留。
