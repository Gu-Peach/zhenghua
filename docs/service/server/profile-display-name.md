# 已发布规则的目录显示名称

规则的用户可编辑名称为extraction_profiles.display_name。profile_key（如custom_…）、版本、ZIP及manifest内的原始名字属于已发布包内容，不随目录改名重打包。上传PDF选项、规则列表/预览标题显示数据库名称；内部skill标识继续保留供搜索和诊断。已绑定项目仍按原profile_id/checksum工作。

新增PATCH /api/v1/rule-library/{profile_id}，输入display_name（去首尾空白，1—120字）及expected_display_name；仅创建者可改已上传目录项。Repository更新条件包含id、created_by与原名称，用于并发冲突保护；重复提交相同目标名幂等，返回ProfileReferenceRead，新增can_rename明确界面权限。重命名不创建新包/版本，无Storage写入或数据库迁移。

实现顺序：DTO/所有权与条件更新 → 列表内名称编辑、Enter保存/Esc取消及错误保留 → 离线API/浏览器及文档。用户尚未指定新名字，本任务增加编辑能力，不代改实际记录。

已完成：5项Server离线回归及16项浏览器通过，覆盖鉴权/空白长度/过期名称/更新竞争、幂等、项目绑定不变、无Storage请求，保存/刷新/取消/失败/只读、资源预览和既有编辑；类型/lint/build、Ruff/3源码mypy与桌面窄屏截图通过。无真实规则改名、写业务库或调用模型/启停服务。重载8000并刷新Web，名称旁铅笔编辑，Enter或保存提交，Esc/取消放弃；无迁移，8100不需重载。
