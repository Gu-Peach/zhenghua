# ADR-0017：独立提取Agent目录

状态：Accepted（用户2026-10-14要求目录迁移，不改实现，只允许引用调整）。

## 目录与边界

目标为用户已有的`services/agent/src/agent/extraction_agent`，Prompt/Profile资源已经在该目录。迁移阶段Agent、文档提取应用/Graph、专属输入输出模型、PDF/图片/JSON/Excel工具、VLM适配器、模板确定性策略及局部提取工具。包括Stage1分类和Stage2初扫/内部补全，它们共同构成当前“两阶段提取Agent”。

API、Supervisor/纠错编排/改进Agent、通用Harness、任务控制/Worker、共享Domain契约、Profile注册/包管理和数据库/Storage通用仓储留在src共享层。共享代码通过新模块引用复用提取能力，不复制实现。

用户已将agent_service包内容搬到带有__init__.py的src根，保持该布局。共享包正式名称随目录改为src，独立实现路径为src.agent.extraction_agent。入口将services/agent加入模块搜索路径，包配置包含src及其子包；旧agent_service导入和patch目标统一更新，不复制实现或建立第二份类型。

## 实施步骤

1. 已完成：记录当前用户工作区的61份迁移源码、254份Python引用文件及现有资源字节基线。
2. 已完成：迁移实现，调整导入/patch目标、入口搜索路径、资源位置、包配置及图像资产忽略例外。现有.env仅更新AGENT_PROFILE_ROOT旧目录引用，其他配置不动。
3. 已完成：254份Python文件静态AST比对，去除导入及明确路径引用后无实现差异；源码import目标均可在新目录找到。116份资源逐字节未变，只有3份代码路径/校验和元数据调整。文档/模块索引同步。

模型类名、Schema字段、Prompt/expected内容、函数体、Graph拓扑、校验及数据库行为不改变。仅迁移导致的import/module path、__file__层级、资源路径/校验和及测试引用允许调整。不运行模型、业务测试、数据库或服务；静态审阅不等于真实运行验收。
