# 本地提取脚本切换agent_test整页试验

按用户要求保留其`agent_test/extraction_agent`副本，并将仓库根`/agent_test/`整体Git忽略。两个本地入口`run_stage2_groups.py`、`run_page_workflow_extraction.py`在CLI启动且提取模块尚未导入时，通过独立加载器选择该副本；副本内部原绝对import保持，application、graph、模型适配器、Profile策略与资源均从副本读取。缺目录或已混入正式模块时停止，不自动重建或回退。实现与命令见[说明](../local-extraction-test-runtime.md)。

共享配置/模型Gateway/注册器继续使用已安装服务库；CLI强制memory、关闭远端包并清空数据库凭据。启动打印实际代码路径，分组input_manifest记录代码与Profile目录；默认输出迁入agent_test/runs/stage2，独立试跑建议新目录/run-id。

## 仅修改测试副本的ZH

- 测试ZH2.3.1、manifest v16，关闭completion_view.enabled，目标图和补全Few-shot都使用整页，不按引用列裁剪；坐标按整页归一化，原长边与总像素预算保持。
- 初扫放线标记→直接端子→当前段原理号line_number；unit.wire_number=null。副本Prompt、调用指令及JSON Schema提示同步，原理号要求明确输出（未知null）。
- 新增002C03/PDF50同页16条，沿用此前已核对原图和用户1641.xlsx第16～31行的本地快照；保留两个003G0121支路。原003C01和7个补全/重复N负例保持，未知/控制电流为空。
- 跨页先回指再核对初扫原理号；无回指时允许按原理号、信号/对象/拓扑唯一匹配，异源回指或原理号冲突不能绕过，不修改冻结起点。

## 验证

30项相关离线测试通过，含新进程启动两个CLI后的所有提取模块来源、缺失/混用失败保护、2个初扫与7个补全真实图片Fake回放、明确line_number/wire_number Schema、实际目标与补全示例整页比例、终点/元件/依据/不确定性/电流及整页坐标字段对照。测试禁止HTTP请求，未调用真实模型。

实际分组CLI预检读取1来源页和679张可用图，输出打印测试路径并生成本地input_manifest，无模型调用。测试Profile本地包40文件、Schema/路径和来源摘要校验通过；新增图像与原002C03字节一致，207个正式提取目录文件摘要保持。

修改文件Ruff通过，新加载器及PDF入口mypy通过。分组脚本整体mypy仍有10项既有XML可空/Any返回类型错误，HEAD基线对照错误及数量相同，本次未扩大修改。回归中一项旧Fake补全响应缺source_note，补齐既有证据契约后通过，不放宽实际响应校验。

未修改正式extraction_agent、数据库已发布包、项目引用或Worker/Explain入口，未上传数据库/Storage、执行真实提取或启停服务。并行Explain开发改动保持。副本内容和试跑结果被Git忽略，新的checkout需自行复制并配置测试规则；真实视觉准确率和整页耗时待用户显式运行上述命令验收。
