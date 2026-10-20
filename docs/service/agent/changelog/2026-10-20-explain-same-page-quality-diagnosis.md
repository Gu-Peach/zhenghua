# Explain 同页重扫质量诊断（仅诊断，未修复）

后续用户已授权实施，[ADR-0042修复交付](./2026-10-20-rescan-requirements-routing.md)完成代码/离线验收，真实模型质量待新任务验证；以下保留原诊断与当时状态。

## 已核实

本次只读对照冻结任务、checkpoint中的四次模型返回、候选与确认后的数据库行。请求要求五个起点集合、同页终点和原理号，实际任务仅包含四个已有行ID，fields=end、局部patch。一个缺失起点未进入任务，额外旧行不在修改范围内。模型说明中保留了补提原理号的要求，但端点补全数据模型没有line_number输出，候选字段掩码也禁止end模式更新principle_number，因此无法靠说明文字完成该要求。

四次模型调用均有返回；两条终点为空，两条非空，其中一条与用户完整图纸的线路对应关系不符。四条候选变更中包含两条清空旧终点，“拟修改四行/已保存”不能表示四条均成功识别。缺口ID与变更行有交集，界面“未唯一匹配”的文案不能准确区分行身份匹配和终点未识别。

字段end会直接调用rescan_ends并跳过本页扫描，该函数复用定向跨页补全。ZH目标图补全提示要求先找来源页回指；在来源和目标为同一页时仍使用此规则，现场空结果明确报告找不到跨页回指，其他返回也有沿错线路现象。物理页与业务页索引读回一致，不能将此处归因为图纸目录页号错误。

本轮Explain日志为正常tool_calls并返回多个工具调用，任务最终成功并已确认保存。截图红卡是创建工具某次调用失败，不能据此认定Worker的四次识别均失败；单次失败工具的参数/完整错误未保存在该诊断摘要中，确切原因需要完整工具结果，不能套用前次required错误。

## 对应代码

- `services/agent/src/agent/explain_agent/prompts/explain.md`：本页终点提示直接指定fields=end，未充分区分纠正起点集合与额外字段要求。
- `services/agent/src/agent/explain_agent/rescan_execution.py`：end模式冻结已有行并进入rescan_ends，未处理缺失起点创建；同页任务复用resolve_cross_page。
- `services/agent/src/agent/extraction_agent/infrastructure/zh_vlm_stages.py`：目标图补全指令以回指匹配为前提。
- `services/agent/src/agent/extraction_agent/domain/models/extraction_stages.py`：CrossPageCompletionData没有原理号输出字段。
- `services/agent/src/agent/explain_agent/rescan_candidates.py`：end掩码只允许终点及相关复核/页面字段，不允许principle_number。

## 修复顺序（尚未实施）

1. 任务规划区分“保留既有行、仅补终点”和“纠正整页连接集合/补漏/提取其他字段”。后一类使用已有整页fields=all/replace_scope候选流程，不能截取已有行ID后声称覆盖用户全部起点；缺失连接不得编造ID。
2. 同页仅补终点应采用适用于本页放线段的识别路径，不能强求跨页回指；保留起点、Profile隔离、坐标和不确定性约束。涉及Profile规则调整时按版本化案例与发布流程处理，禁止直接改生产包。
3. 区分工具尝试、任务执行完成与字段识别完整性；未确认终点/缺失起点/无法匹配分别报告。不能把变更条数当识别正确数。

本轮没有修改产品代码、Profile或正式数据，没有真实模型调用、重扫重跑、任务恢复或服务启停；只读快照保存在忽略的.runtime目录，不纳入版本化资产。未运行测试：本轮仅定位与文档归档，尚未实现上述修复，也不声称模型质量已恢复。后续必须增加范围、同页线路、原理号字段和缺口呈现的失败回归，再进行实现与验收。
