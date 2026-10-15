# Extraction Agent

当前ZH本地版本2.0.5：端点确定后可另沿相线查对应断路器Ie明确电流，不改变端点/坐标，详见[电流记录](../../../../../docs/service/agent/changelog/2026-10-15-zh-ie-current.md)。元件标识按同页附近/Object Loc或跨页对应引用/附近/Object Loc读取；source_component只完善元件元数据。最终记录保留start_terminal_coordinates/end_terminal_coordinates，本地XLSX14列，见[坐标记录](../../../../../docs/service/agent/changelog/2026-10-15-zh-c01-terminal-coordinates.md)。

这是当前Stage1页面分类及Stage2逐页提取的独立代码目录。Stage2内部包含初扫、定向双图补全、校验和完成页保存。迁移只调整代码位置与引用，不改变提取规则、模型结构或Graph行为。

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
