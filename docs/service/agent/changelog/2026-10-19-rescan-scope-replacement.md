# 重扫候选按范围替换

用户明确要求全部重扫删除所选旧范围、局部仅替换局部。Tool程序根据scope/fields设置result_mode：fields=all且没有行ID/原理号限定时为replace_scope；按行ID/原理号或单侧字段为patch。模型工具Schema不暴露该选择，传入错误模式也由程序纠正，工具活动显示实际模式。旧DTO默认patch可读，但旧版大范围all候选不能继续按合并方式确认。

全量候选不再依赖旧行匹配，包含全部待删除旧行和全部新结果，使用新行ID。每页必须成功提交扫描检查点，页失败/覆盖不完整或输出越界则不生成可确认替换；成功的空结果明确提示确认后删空范围。局部继续匹配选中行/限制字段，不插入其他扫描结果，未定位的行说明未修订。Stage2/Profile和多图证据适配不重写。

新增强类型RescanRemovedRow/RescanReplacement及请求result_mode，Server DTO、OpenAPI和Web已同步。缓存契约升为rescan-v3，固定result_mode；旧缓存需新任务。replacement.version显式置1，保证exclude_unset保存仍带版本。Explain事实包提供真实删除/写入数和前20条摘要，模型只说明候选、不持有提交工具。

117项相关Fake/Mock通过（含ZH/当前局部模式/ABB的真实Graph假网关替换路径、7旧行→6新结果、不完整页/空结果/局部保护/模式程序控制/持久化版本），Ruff和Explain包18源码mypy通过。未运行真实模型或提交实际业务候选。

本地新迁移已安装，启用仍需用户重载8000 API2.10.0、8100及实际Worker（inline只重载8100宿主），刷新Web并新建重扫。旧7行并未自动清理，只有新预览确认后才执行。见[ADR-0036](../../../adr/0036-rescan-scope-replacement.md)。
