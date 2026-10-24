# agent_test ZH来源引用精读与目标整页补全

2026-10-22，按用户授权完成本地代码/规则编辑，设计见[改造方案](../zh-source-reference-refinement-plan.md)。本地Profile为zh2.4.0；未执行验证、测试或真实模型，不能宣称准确率改善已验收。

## 实现

- 新增refine_source_references页内Graph节点，位于整页初扫和任务规划之间。dispatcher/Graph client按Profile资源启用，其他未配置规则保持原模型操作路径。
- DrawingReference增加来源引用区域和程序专用证据；定位、精读使用独立Pydantic模型，模型输入不信任验证状态或物理页。整页初扫没有框时，优先用可用PDF文字坐标的唯一明确匹配，否则单独模型定位；按原图裁取补边、合并重叠区域并按ID读取。
- 来源区域内PDF文字可核对精读原文；冲突/缺项/格式错误保留原因，不凭目录存在猜地址。不具备原PDF的旧分组缓存退到高清图像精读；不自动寻找其他PDF代替。
- 仅回写已有连接引用和有图像证据的完整信号，冻结起点/坐标/方向/原理号和连接集合。已标cross_page但无引用的连接可用空引用进入定位，不为SPARE/PLC标签猜引用。
- 目标物理页只来自唯一分类业务身份，并在任务创建前核对实际目标图片身份；不接受模型物理页。ZH列限0到9。关闭目标裁剪，按整页追指定连接并输出整页坐标，保留回指/完整信号/原理号多证据匹配。
- 新模型操作stage为source_reference_locate/source_reference_read，走既有Gateway和日志/缓存。运行agent/source-references/<页号>/保存局部PNG及references.json，完成页包含更新后引用及确认计数；诊断保存失败只记录安全警告。取消在批次边界检查。

## 保留与限制

正式Agent/API/数据库/Storage规则包、服务及历史结果不改，agent_test仍Git忽略。既有3目标图/4补全正例不改事实，无负例。新增精读阶段没有新增未经人工确认的图像案例，采用Schema+Prompt；其质量待用户实测。

目标整页仍按现有2048输入长边和总像素预算发送，未提高预算，不能承诺小字全部清楚。新增定位/精读调用增加耗时和模型用量。未运行路径/Schema/语法/类型/lint检查、pytest、Fake VLM、打包或真实模型，也没有改用户现有结果。

## 用户实测

使用既有命令并显式指定--agent-source test --profile zh；新输出目录/run-id避免混入旧产物，本地README已同步zh240示例。重点看日志source_reference_refinement计数、局部图是否包含正确箭头、references.json的initial_raw/reading_raw/pdf_text_raw/status，以及目标调用completion_image_view.mode是否为full_page。
