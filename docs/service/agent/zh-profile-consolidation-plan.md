# ZH正式规则归拢

## 当前整理约定：源码单份资源

2026-10-19用户指出profiles/zh/resources与prompts/zh重复，明确要求清理。以下旧“源码自包含”的布局调整为：

1. 已完成：已验证Prompt/案例统一放回prompts/zh，Profile使用受控本地引用；保存字节/消息基线并移除resources重复副本及旧补全Prompt。
2. 已完成：zh_crop测试引用和当前文档同步，60项摘要更新；不恢复用户删除的zh_crop/history。
3. 已完成：本地ZIP及自包含加载/Server解包通过，30资源/10策略源码/本地9组与冻结包9组消息一致；未运行pytest/Fake VLM/模型、不上传或改业务数据。

正式版本仍为zh2.3.0，本次仅调整尚未发布的本地布局。已有冻结包不改，Python策略/裁剪参数/提取Schema保持。

以下为首次整理的历史计划，源码布局以本节及[最新交付](./changelog/2026-10-19-zh-source-cleanup.md)为准。

2026-10-19，用户已确认zh_crop准确性，要求整理zh与zh_crop以便后续规则包上传。

## 设计与范围

- 正式入口为 `zh@2.3.0`，仍绑定现有 `zh_native`。Python策略本来位于 `profiles/zh`，不迁移或改写算法，XMZ继承路径保持。
- `profiles/zh/resources/` 收拢已验证的初扫/分类/局部补全Prompt、分类案例与zh_crop的1初扫/7补全案例；根目录保存routing rules与completion view配置。正式Profile的全部资源引用限制在自身目录，使用packaged模式。
- 新Prompt、图片、Expected/任务输入及裁剪配置逐字节沿用zh_crop2.2.1；只调整正式Profile身份/展示与资源位置，不改变模型消息内容或裁剪算法。
- 旧zh_crop2.2.1及prompts/zh资源保留作历史兼容/对照，不删除、不自动改绑定、不修改冻结任务。新的`--profile zh`使用2.3.0；显式zh_crop命令保持可运行。旧zh2.1.1已冻结的包保留原资源，未冻结的旧版本任务仍受原版本/摘要保护，不自动套用新规则。
- 上传资源包不包含可执行Python；部署环境继续提供注册的zh_native策略。沿用既有build_package/verify_package，不建立第二套打包协议、不实际上传或发布。
- 本地生成忽略的ZIP及manifest校验信息，供后续上传准备。新增README/CHANGELOG说明正式入口、资源与运行代码边界。

## 执行顺序

1. 已完成：记录原资源摘要，收拢正式资源与配置，保留旧入口；原2.1.1元数据留历史快照。
2. 已完成：同步受版本提升影响的回归断言，补齐资源/封装一致性回归；31份资源与9类Few-shot构造相同。复用已有分类别名兼容校验，不改样例原文。未运行测试或模型。
3. 已完成：本地ZIP及独立加载/Server解包校验通过，入口与交付文档已更新；实际上传另由用户发起。
