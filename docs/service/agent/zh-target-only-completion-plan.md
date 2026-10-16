# ZH 目标图定向补全

2026-10-15，用户确认实施，仅修改本地规则与代码，不发布、不写数据库、不运行测试或真实模型。

## 契约与边界

Stage 2 初扫仍以放线标记定位两侧直接端子及方向。原有 drawing_function、drawing_page_number、drawing_object_location 和 references 继续使用；连接新增可选 signal_name，只保存对应线路/箭头旁可见的信号或电位名称，不从元件功能生成。

Profile extraction 增加 cross_page_input_mode，默认 source_and_target 保持旧包、ABB、XMZ 的双图行为。本地 ZH 新版本选择 target_only。Graph 按客户端能力跳过来源图片加载，任务仍保存来源、目标的业务页标和 Object Loc；适配器将 state 中的来源事实整理为 Pydantic 任务上下文，仅发送目标图。无需改变工作流拓扑或跨页任务粒度。

目标图从来源业务工作区/页码、对象位置回指定位候选，再结合原理号、信号名和任务引用匹配，沿实际导线读取最近端子。PE、N、重复原理号或同页多路信号不能仅靠一个重复字段配对。未唯一确认置空并 needs_review，不自动重读来源图、不阻塞下一页。

起点端子、坐标、原理号、方向和已有电流冻结；沿用可选 source_component 仅补元件元数据。终点坐标属于目标图片物理页。扫描失误不会被这次补全改造自动纠正。

Few-shot 的补全输入与真实调用一致：目标图加来源结构化事实。扫描例保留真实来源图。新增字段进入 JSON/state，不增加 XLSX 列。版本/checksum、文档及回归文件同步，真实精度与耗时由用户新目录复测。

## 执行顺序

1. 设计与任务登记（完成）。
2. Profile 模式、上下文、Prompt/样例与回归文件（完成）。
3. 静态语法/资源/Schema/类型核对及文档收尾（完成）。具体结果及未运行项见[changelog](./changelog/2026-10-15-zh-target-only-completion.md)；实现完成不代表真实模型质量验收。
