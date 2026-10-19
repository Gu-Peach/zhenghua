# ZH源码资源去重

用户明确要求保留原有profiles/prompts分工，清理本轮整理产生的重复副本。

## 当前布局

- `profiles/zh`：zh2.3.0身份、路由/裁剪配置、Python策略、当前来源摘要和说明。
- `prompts/zh`：唯一维护三阶段Prompt、分类案例及1初扫/7跨页案例。局部补全统一使用 `page_connection_completion.md`。
- 上传生成包：既有build_package收集外部声明资源，自动生成包内resources并封装Schema和manifest；部署侧仍需zh_native。

移除已逐字节验证完成迁移的profiles/zh/resources副本、重复page_connection_completion_crop.md及旧样例过期quality-provenance。有效裁剪参数、图片/Expected/任务和Prompt内容均保持迁移前正式版本。用户先前已移除的zh_crop/history不恢复，相关测试改用正式zh，不增加兼容别名或自动改写历史任务。

本地Profile的resource_mode使用既有legacy_reference字段，表示资源位于Profile目录之外，不表示提取规则降级；生成包仍为packaged模式，无运行时源码目录依赖。

## 验证与产物

- 30份Prompt/样例资源逐字节一致，10份ZH Python策略及裁剪配置摘要不变。
- 迁移前/后9组本地Few-shot构造、9组独立冻结包Few-shot构造完全一致；没有调用Gateway或模型。
- ProfileRegistry/Server本地目录加载、Agent封装/结构/摘要校验和Server解包通过，包内引用全部自包含；38清单文件，ZIP含顶层manifest共39文件，约2.10MB，不含Python。
- 60项来源摘要、6文件AST/Ruff及两CLI帮助检查通过；测试引用已同步，未运行pytest/Fake VLM或真实模型。
- 源码资源不再出现profiles/zh/resources。新005c01.png位于已有版本化Prompt资产白名单中；测试产物/ZIP/基线备份均在被忽略的.runtime中。

最新本地ZIP为 `.runtime/zh-source-cleanup/zh-2.3.0.zip`，校验摘要在同目录verification.json。未上传、写业务库/Storage、重启服务或重跑任务。版本仍为尚未发布的本地zh2.3.0；使用`--profile zh`，持有旧Profile目录缓存的服务需由用户重新加载。

此记录替代[首次整理](./2026-10-19-zh-profile-consolidation.md)中“源码资源自包含/保留zh_crop”的早期布局约定，提取规则内容保持。
