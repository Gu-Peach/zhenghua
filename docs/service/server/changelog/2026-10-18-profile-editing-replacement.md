# 规则编辑代理与新版替换

2026-10-18，API版本2.6.0。设计见[ADR-0032](../../../adr/0032-profile-resource-editing.md)。

浏览器在查看规则时通过`POST /api/v1/profile/references/{profile}/draft`请求编辑草稿；Server验证所有权、当前版本和摘要，从可信DB引用下载校验包或绑定本地资源，再调用8100受信导入。新增editor状态/文件保存/核对/公开工具流/建议确认代理；身份只来自JWT，不相信浏览器同名用户字段。编辑流强制discuss，不能跳过用户确认。公共DTO从Agent生成，OpenAPI及TS同步，未新增端口或环境变量。

已确认修改的编辑草稿发布时调用新`replace_extraction_profile`，事务内校验来源仍当前、所有者、版本单调与幂等，并发布新不可变ZIP引用。规则列表仅展示同key最新版本，历史ID仍可供原项目读取。旧版本有项目引用或未结束/失败任务快照时保留；无引用旧登记删除并进入`profile_asset_gc`队列，Server随后按拥有者和严格Storage路径删除对应ZIP。队列RLS限制用户只读自己的记录，只有可信服务能回收；退役引用阻止重新登记已排队删除的旧包。

清理失败仍返回发布成功和cleanup_pending，队列在后续发布或`POST /api/v1/profile/cleanup`中重试；先检查没有规则引用再删对象。不会删除项目目录、任务冻结包或别人的对象。DB与Storage无法跨服务原子提交，因此保留待清理记录而不是把清理失败当发布失败。权限/来源过时/版本冲突保持明确失败，不覆盖同版本。

新增迁移`20261018010000_profile_editing_replacement.sql`，未改旧迁移。空库/带旧快照的独立无网络数据库测试覆盖RLS、项目/任务保留、无引用回收、旧包复活保护、过时及跨用户发布、幂等。测试后已原子应用到明确的本地`supabase_db_zhenghua_test`并登记历史；事务内项目、规则、线表和Storage摘要相同，队列0条。REST Schema已能看到新函数/队列，未执行替换发布或删除真实包。私有部署校验在忽略的`.runtime/profile-editing-deployment.json`。

26项Server回归通过，含真实Agent TestClient+Fake模型的Storage/本地派生、人工保存/核对/新版发布、清理失败后重试；2项独立SQL通过。Server/Agent DTO、类型与静态检查通过。只读探活确认运行中8000仍2.5.0、8100未加载imports，需要用户自行重启两者；没有启停用户服务或重跑提取。
