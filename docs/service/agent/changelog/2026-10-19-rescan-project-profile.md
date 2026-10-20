# 重扫使用项目明确选定的新规则

用户希望已绑定ZH2.3.0的项目重新扫描时实际使用新版。按[ADR-0040](../../../adr/0040-rescan-project-profile.md)新增项目级显式策略，仅为该项目开启；其他项目默认仍用历史规则。

Worker的RescanSnapshot保留profile_source/profile_id。project_reference任务仅加载入队时固定的Storage ZIP，校验引用路径、归档checksum、包内资源及key/version；不会读取原批次profile-package，也不回退本地规则。historical及无标记旧任务仍走原逻辑。缓存契约rescan-v5隔离此前完成页与模型产物，既有已应用任务不改写；旧配置断点需重新发起任务。工具描述/聊天Prompt同步以真实回执profile为准，模型不能靠文字改变项目策略。

验证：先补7项包加载/Worker快照回归，6项在旧实现失败；修复后通过。主助手、重扫与Server默认173项通过、50项显式集成默认跳过；另16项不同隔离SQL分批通过。Ruff、3个Agent源码/部署脚本mypy、公开OpenAPI一致性通过。实际2.3.0包已只读通过Worker加载函数，明确拦截旧批次访问，未调用模型。

数据库迁移与项目策略均已生效，真实入队函数在最终回滚事务中验证返回zh2.3.0；没有留下重扫job。用户重载实际Worker后重新发送重扫，内嵌Worker则重启8100，独立Worker需单独重载。8000无需为本次SQL变化重启。实际线表和旧任务保持，候选仍由用户确认。

没有修改提取算法、原Profile资源、前端或公开DTO；未运行真实模型/浏览器验收或启停服务。用户重新发起时会调用其已配置模型，质量仍需人工核对。
