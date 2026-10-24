# agent_test ZH规则适配

2026-10-22，按用户授权仅完善agent_test中按ABB结构精简的ZH规则，保留用户自行实测的安排。

## 改动

- 本地zh规则标记为2.3.2，仍使用zh_native。初扫契约恢复PageScanData，移除ABB小圈两侧编号、原理号留空和拼Sheet要求；读取ZH图上的完整原理号，未知为空，同号分支按实际端点分别保留。
- 本地zh_vlm_stages.scan_instruction和rules.json同步原理号口径。初扫明确实际端子/元件、完整信号名与页级身份；引用分别保存工作区、对象、业务页和列，修正示例+01F11被解释为+01F26的问题。
- 电流恢复Ir优先、其次In/Ie及对应原文，未知三项为空，逐连接处理。补全仍冻结来源原理号、端子及方向。
- 保持当前receiver逐连接过滤和列裁剪配置；不修改Few-shot图像/Expected、公共Schema、正式Agent、数据库规则包、服务或既有结果。

## 使用与限度

沿用现有本地PDF/分组脚本，显式使用`--agent-source test --profile zh`，每次选择新的output-dir/run-id。本轮没有新增CLI参数；本地README含用户提供PDF的命令。

按用户要求未运行验证脚本、测试、类型/lint、打包、真实模型或回归集，不声明质量通过。completion_view.provenance.json仍是继承的2.3.0历史来源快照，不代表本次验收；agent_test整体Git忽略。方向归属及实际提取效果由用户实测，本次没有改变信号方向与线表方向的既有关系。
