# agent_test ZH整页初扫与最近端子复扫

2026-10-22，按用户最新要求完成本地zh2.5.0代码/规则编辑，设计见[两阶段方案](../zh-segment-two-pass-plan.md)。替代本地2.4.0来源引用精读实验；没有运行验证或真实模型，实际识别质量待用户实测。

## 改动

- 移除source_reference_locate/read Prompt、源图裁剪/定位读取模块、专属Schema、Graph节点、client和dispatcher入口及Profile资源，不再触发两种来源模型调用。原始run/诊断产物不删。
- 初扫PageScanData增加segment_evidence，记录放线斜杠及两侧最近边界/依据。PageScanner按Profile的segment_trace_rules启用门禁，明确无标记的连接不纳入；两端在本页优先same_page，边界不明不猜跨页。
- 引用显式分型，元件关联和不参与路由的旁路信息单独保存component_references。只有本段真实wire_continuation且有路径依据进入目标任务；同页及unknown不因为旁边有合法地址就跳页。
- 复扫CrossPageCompletionData及对应Result增加nearest_terminal与terminal_stop_basis，程序以模型明确返回的最近端子赋end，不解析自由文本提取端子。缺结构字段进入既有有限Schema重试；未知保持空，不能靠相邻线补造。
- 起点整个对象、原理号、方向和初扫同页终点冻结；复扫source_component只能为null，合并器不改来源对象、也不覆盖已确认end。目标仍整页、物理页仍唯一业务身份定位并核对图像，输入长边/预算保持。
- 初扫与复扫Prompt、动态Schema约束及manifest v18同步。保留现有003C01整页/4补全正例、3目标图共享展示，无负例；只增加对应已确认事实的边界/引用类型/最近端子字段，原端子/坐标/原理号不变，旧补来源元件Expected设null。

## 边界与实测

仅agent_test及文档，正式Agent/公共API/数据库包、服务和既有结果保持。其他没有segment_trace_rules资源的Profile继续缺省路径。Pydantic门禁约束模型声明与路由，不等同于程序实现了确定性图像追线，无法保证模型的视觉边界判断必然正确。

按用户既有约定，未运行验证脚本、pytest/Fake VLM、类型/lint、打包或真实模型。没有将本次编辑写成质量已验收。新增结构字段可能使用既有校验重试，用户运行时记录usage/耗时。

沿用--agent-source test --profile zh及新输出目录/run-id；本地Profile README已给zh250的002.C/003.C/004.C及完整PDF命令。检查初扫segment_evidence和component_references、是否仅真实跨页进入cross-page-tasks、补全nearest_terminal及最终end是否一致，不应再出现source_reference_locate/read阶段。

## 后续用户授权的002.C实测

同日用户明确要求“再测试一下002.C”，因此执行真实模型测试；上文未运行项描述的是本次编辑交付时的状态。未修改提取代码、Prompt或模型配置，也未运行额外回归/类型/lint。

运行命令：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py --agent-source test --profile zh --groups 002.C --output-dir agent_test/runs/zh_250_002c_001 --run-id zh-250-002c-001 --allow-real-model
```

实际加载agent_test/extraction_agent，zh2.5.0，Qwen3.8 27B。7个来源页为PDF48/49/50/51/52/53/54，业务页1/2/3/5/6/11/21。流程结束、XLSX成功导出，57条中38条有终点、19条为空；状态待复核41条。耗时333.446秒，32次真实模型调用、无缓存命中或接口失败；总量521966 tokens（输入465183、输出56783）。服务未给价格，未推算费用。未上传数据库或Storage，旧运行目录保留。

| 业务页 | 记录数 | 同页 | 跨页 | 有终点 |
| --- | ---: | ---: | ---: | ---: |
| 002C01 | 6 | 0 | 6 | 4 |
| 002C02 | 8 | 0 | 8 | 8 |
| 002C03 | 15 | 14 | 1 | 14 |
| 002C05 | 8 | 0 | 8 | 4 |
| 002C06 | 9 | 0 | 9 | 0 |
| 002C11 | 9 | 0 | 9 | 8 |
| 002C21 | 2 | 0 | 2 | 0 |

本次仅检查现有结构化结果与调用日志，没有逐条对照原图，终点非空不等于正确：

- 002C03保留14条同页，X3:23/29/28到XD21:7/8/9的同页端点已输出；仅1条生成跨页任务，相比此前整页误跨页的情况有改善。
- 002C06的9条引用全部未解析出目标页。例如raw为`=01F10/11.1 / -TA2_U2`，目标函数缺失且地址与信号混写，程序返回`source reference has no single complete literal address`，没有进入目标图补全。其余控制线地址被读为`=M+01F11.3/33`等；本轮不临时改规则或覆盖结果。
- 002C11仍全部判为跨页，目标均为业务页21/PDF54，8条终点非空。已知应在本页XD1停止的右侧段仍未作为同页保留，因此本轮不能作为质量验收通过；程序门禁不能纠正模型虚构的边界事实。

产物位于Git忽略目录`agent_test/runs/zh_250_002c_001/`：result.xlsx、records.json、run-result.json、page-scan-results.json、cross-page-tasks/results.json和model_calls/20261022T130232535499Z。未提交运行结果或原始模型日志。
