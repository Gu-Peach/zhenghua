# 三阶段确认后的不完整样例发布

用户明确允许已走到末尾的规则先发布，后续再校验。对三阶段均已人工确认的Wizard草稿，将POSITIVE_CASE_MISSING（初扫未确认来源端子）降为warning，不阻止导出/发布；识别出的空字段和needs_review原样保留，不补造起点或终点。不完整提示保留在校验输出与页面。

ValidationIssue新增severity，缺省error，兼容旧输出；ValidationReport.ready由是否存在error决定。未完成三阶段的草稿仍不能发布；资源/图片/Schema无效、未确认Expected、版本冲突、权限等原校验保持。本次仅放宽已确认流程中的接线样例完整度，不自动发布实际用户草稿。

执行：先补校验/导出复现测试 → 校验及契约同步 → 页面提示与回归 → 文档。无业务库迁移，已有项目/正式规则保持。

已完成：7项Agent校验回归、6项Server鉴权/真实打包后Mock发布回归和3项浏览器通过，包含空起终点的完整发布/目录预览、正常发布/编辑、未确认/坏资源拦截；类型/lint/build、Ruff/两源码mypy及桌面/窄屏截图通过。只读套用新校验，实际test修订9的publish_ready为true，唯一问题为POSITIVE_CASE_MISSING warning；未修改该草稿或代发规则，无真实模型/业务库/服务操作。重载8000/8100刷新Web，恢复原会话即可发布，无需重跑。
