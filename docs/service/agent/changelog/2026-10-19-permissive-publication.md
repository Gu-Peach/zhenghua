# 三阶段确认后允许不完整接线样例发布

按用户明确指示，Wizard三个阶段均确认后，POSITIVE_CASE_MISSING改为warning，起点/终点为空仍可导出及发布；缺失内容保持原样。未完成阶段、结构/图片/Schema、Expected确认、版本及权限原校验保持。

ValidationIssue增加severity（缺省error），ValidationReport版本升为extraction_stages_v1/review_1.1.0，ready按是否存在error判断。生成同步Server DTO、OpenAPI和TS。页面保留完整性提示；若其他阻断仍存在则如实显示“请检查以下问题”。

7项Agent校验、6项Server回归和3项浏览器通过，含空起终点的实际临时包导出/Mock Storage与发布RPC及目录预览；类型/lint/build、Ruff/两源码mypy和截图通过。只读验证实际test修订9已满足新发布条件，未改实际草稿或代发规则，未运行真实模型/写业务库/启停服务。重载8000/8100刷新Web，恢复原会话即可，无迁移。见[设计与证据](../profile-permissive-publication.md)。
