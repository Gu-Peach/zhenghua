# 新重扫任务独立固定项目规则

迁移20261019030000增加enqueue_connection_rescan的显式项目策略分支：drawing_index.rescan_profile_source=project_reference时，只采用项目当前profile_id的已发布Storage包，固定key/version/checksum/profile_ref/profile_id及来源到job。没有标记仍优先历史行证据。既有job幂等返回早于规则选择，即使项目后续换规则也不改已入队任务。

不覆盖旧批次冻结包。已切换项目允许baseline混合历史规则；新任务固定当前已选版本。默认历史分支原约束保留，选定包必须匹配内容寻址路径及摘要格式。profile_version_in_use增加重扫job引用保护，即使项目后来换版本，其历史任务包也不会被规则替换GC删除。复用原有鉴权、范围/附件/批次/版本和用户确认事务，无新表、RLS或公开DTO。

隔离SQL覆盖空业务表/旧任务迁移、明确升级和默认历史、任务幂等固定/资源在用、越权/本地包拒绝及混合历史版本；新5项与既有11项分批通过。默认173项通过、50项显式集成跳过，公开OpenAPI保持。

本地已通过部署脚本备份Schema、登记迁移并核对业务三表摘要不变。随后仅为用户指定项目启用策略，原配置备份在忽略目录.runtime/project-rescan-profile-20261019；事务核对其他项目字段、线表、重扫job和活动批次产物不变。真实入队函数在回滚事务中返回zh2.3.0，未留下任务，不触发Worker/模型。未重启服务。

部署命令：`.\.venv\Scripts\python.exe services/server/scripts/apply_explain_edits_migration.py --migration 20261019030000 --apply`。项目策略只能由授权管理操作设置，不通过模型参数改变。使用前用户重载Worker并新建任务；以后规则版本仍取项目明确选定版本，不在Worker运行中追随目录最新。

回滚先关闭项目策略并停止新版入队；已固定来源的新任务仍需支持该标记的Worker处理或取消，保留其包。恢复原入队函数使用部署前Schema备份，引用保护无需撤销。历史项目引用替换记录中的“局部重扫仍用旧版”限制已由本次显式策略解除，原批次本身仍为旧版。
