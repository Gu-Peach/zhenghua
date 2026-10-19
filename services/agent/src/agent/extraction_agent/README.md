# Extraction Agent

2026-10-19：正式ZH维护入口为 [profiles/zh](./profiles/zh/README.md) 的2.3.0；Prompt/样例仅维护在prompts/zh，Profile配置引用，打包时生成包内resources。重复源码副本已删除，用户已移除的zh_crop/history不恢复。仍使用zh_native，模型输入/算法保持，见[清理记录](../../../../../docs/service/agent/changelog/2026-10-19-zh-source-cleanup.md)。

2026-10-18后续调整：按用户要求，文档遍历正常返回即提交finished，单页错误保留metrics/诊断及失败尝试；只有真正中断才整任务失败。前端兼容已跑完的旧EXTRACTION_PARTIAL显示完成，见[记录](../../../../../docs/service/agent/changelog/2026-10-18-extraction-finished-status.md)。

2026-10-18：页面子图增加初扫失败分支，保存独立失败尝试后继续后续页，不创建成功缓存；文档遍历结束再汇总未完成项，恢复复用成功页。模型请求/业务规则保持，需用户重启Worker生效，见[记录](../../../../../docs/service/agent/changelog/2026-10-18-extraction-page-failure.md)。

2026-10-18：上传Worker与本地Stage2脚本共用`stage2-script-aligned-v1`请求/结果契约，禁色标提示、页面身份、模型Gateway和主表字段统一；保存过滤前计数与请求指纹，支持ZH第0列。ZH Prompt/样例和2.2.1业务规则不改。使用前重启提取Worker，再新上传测试。见[交付](../../../../../docs/service/agent/changelog/2026-10-18-extraction-entry-alignment.md)。

2026-10-17：ABB1.2.0与XMZ（规则键zh_gantry_reel）0.2.0对齐目标局部补全，初扫各一张来源样图，补全只用对应目标图；分类不改。纯裁剪/精简任务机制位于`infrastructure/document/completion_*.py`，原ZH路径保留兼容导入。见[交付记录](../../../../../docs/service/agent/changelog/2026-10-17-abb-xmz-alignment.md)。

原zh_crop2.2.1的按列局部补全、整页坐标回映、有限空响应校验重试和重复N线匹配现已纳入正式zh2.3.0，运行时仍只选一个补全案例。新测试命令使用`--profile zh`；旧实验目录不再作为运行入口，测试产物继续忽略。

2026-10-16新增`application/incremental_worker.py`和`infrastructure/incremental_repository.py`，为Stage1/Stage2接入三表增量发布与租约恢复；`application/review.py`统一生成复核原因，模型输出只保留事实。旧CLI仍默认内存，不自动写库。在线启动见[Agent README](../../../README.md#当前增量提取的启动方式)，设计见[ADR 0022](../../../../../docs/adr/0022-incremental-extraction.md)。

当前ZH本地版本2.1.1：目标图补全上下文v2只传来源匹配事实与元件元数据，不传来源端子/坐标/方向描述；匹配任意边界回指，沿线分别读目标接口与针脚，缺失地址可由唯一来源页PDF引用核对。ABB1.2.0/XMZ0.2.0也使用目标局部图+来源事实，图框与业务语义独立。见[修正记录](../../../../../docs/service/agent/changelog/2026-10-16-zh-cross-page-reading.md)。端点确定后可另沿相线查对应断路器Ie明确电流，不改变端点/坐标，详见[电流记录](../../../../../docs/service/agent/changelog/2026-10-15-zh-ie-current.md)。元件标识按同页附近/Object Loc或跨页对应引用/附近/Object Loc读取；source_component只完善元件元数据。最终记录保留start_terminal_coordinates/end_terminal_coordinates，本地XLSX14列，见[坐标记录](../../../../../docs/service/agent/changelog/2026-10-15-zh-c01-terminal-coordinates.md)。

这是当前Stage1页面分类及Stage2逐页提取的独立代码目录。Stage2内部包含初扫、按Profile配置的定向补全、校验和完成页保存。迁移只调整代码位置与引用，不改变提取规则、模型结构或Graph行为。

| 目录 | 职责 |
| --- | --- |
| agents | 页面分类、扫描/补全模型操作 |
| application | 完整提取入口、适配器调度、文档运行上下文、阶段持久化 |
| graphs | 页面/文档LangGraph、初扫、跨页、归一化、导出 |
| domain/models | 提取输入输出、端点/连接、图纸索引、图像载荷 |
| infrastructure | VLM适配器、PDF/图片/JSON/checkpoint/Excel工具 |
| profiles | 模板Profile资源、ZH/ABB/大车卷盘确定性策略和导出规则 |
| prompts | 原有Prompt、图片Few-shot、expected及资源元数据 |
| tools | 局部提取执行及完整提取proposal构建 |

Python入口：`src.agent.extraction_agent.application.page_workflow_extraction.run_page_workflow_extraction`。独立页Graph：`src.agent.extraction_agent.graphs.document_extraction.page_extraction.build_page_extraction_graph`。

共享API、配置、Harness、任务控制、Profile注册/包管理及通用数据库/Storage适配器留在services/agent/src，通过src.config、src.harness、src.domain等引用；不复制第二份实现。

现有测试脚本仍是services/agent/scripts/run_stage2_groups.py，参数不变。命令见[本地测试说明](../../../../../docs/service/agent/local-stage2-group-test.md)。服务入口已改为src.main:app，模块搜索根是services/agent。

2026-10-14迁移只做静态路径/AST/资源字节对比，未运行业务测试、模型、服务或数据库；实际运行由用户验收。见[迁移记录](../../../../../docs/service/agent/changelog/2026-10-14-extraction-agent-directory.md)。
