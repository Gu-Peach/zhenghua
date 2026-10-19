# ZH正式规则整理与上传准备

后续用户要求源码资源仅维护在prompts/zh，profiles/zh引用，打包时才生成resources；用户已移除zh_crop/history。以下为首次整理记录，当前布局与最新ZIP见[源码去重记录](./2026-10-19-zh-source-cleanup.md)。

用户确认zh_crop准确性后，正式入口归拢为 `zh@2.3.0`，显示“振华电气图纸 · 2.3.0”。规则身份和资源布局调整，提取策略不重写。

## 结构

- `profiles/zh/resources/`收拢三阶段Prompt、2个分类样例及原zh_crop的1初扫/7跨页样例；全部31份提取资源/裁剪配置与已验证版本逐字节相同。
- `profile.json`使用packaged资源模式，全部声明资源位于profiles/zh内；routing rules与completion view配置归到根目录，附README/CHANGELOG和59项来源摘要。
- 原有ZH Python策略继续留在profiles/zh；zh_native和XMZ继承路径不变。上传包只包含声明资源及Schema，不包含Python代码。
- 保留zh_crop2.2.1原运行资源及命令；旧prompts/zh保留历史对照。原zh2.1.1的profile/rules原始字节保存在profiles/zh/history/2.1.1，供审阅；非新的注册入口。已冻结旧任务不修改，不自动重绑或重提取。

打包时发现旧分类样例仍使用page_number别名，运行适配器原已支持，但Profile发布结构校验没有复用同样的兼容处理。现校验复用已有canonical_expected函数，保留原样例原文；冲突别名仍拒绝。未改变模型输入或Schema字段。

## 验证

- 31份资源/配置逐字节一致；2.2.1旧运行资源、原ZH策略代码及ABB/XMZ基线无意外改动。
- 分类、初扫及7组补全共9种Few-shot消息构造与旧版本完全一致，未调用模型Gateway。三阶段Prompt和规则业务内容相同。
- 本地包37份清单文件，ZIP含顶层manifest共38文件，约2.10MB；通过Agent封装/摘要校验、Profile Agent结构及别名冲突检查、独立目录加载和Server实际解包校验。
- 16项历史图像/案例摘要、59项正式来源摘要、Server本地目录的正式/兼容版本选择、5文件AST及Ruff、校验器定向mypy和两CLI帮助通过。
- 回归代码已同步正式版本、资源一致性和封装边界；按用户惯例未运行pytest、Fake VLM或真实模型。旧质量基线仅用于核对历史资产，当前运行源码使用正式来源清单，避免将过期2.1.1源码摘要误认为当前运行版本。

本地资源包：`.runtime/zh-consolidation/zh-2.3.0.zip`。对应校验报告：`.runtime/zh-consolidation/verification.json`。包为未发布本地产物，未上传数据库/Storage、未改变现有项目、未启停用户服务。

## 使用

后续新任务选择 `振华电气图纸 · 2.3.0` 或脚本 `--profile zh`。已有zh_crop命令仍可使用，但正式ZH后续维护统一到profiles/zh。重载持有Profile目录缓存的服务后刷新规则列表；已有任务继续使用原冻结包。规则包部署环境需已提供zh_native策略，不能通过ZIP上传任意可执行Python。

设计见[执行计划](../zh-profile-consolidation-plan.md)。
