# agent_test ZH示例按目标页合并

## 本轮方案

按用户要求，仅修改agent_test ZH。示例保持003C01来源的4个现有正例，按目标图片分为080C10、003C31、004C01三组，003C31组同时保留XA:11到XD10:1与N-BAR到N-BAR的独立task_id、来源上下文及Expected。

本地manifest通过completion_example_presentation=target_page启用分组。每组第一条示例发送一份整页目标图，后续同组示例通过文字沿用前图；各条仍独立发送来源任务与单任务CrossPageCompletionData答案，task_id保持对应，不引入多任务结果格式。分组示例不做逐任务列裁剪，原Expected整页坐标和各任务引用保持，避免同图不同裁剪坐标混用；当前实际任务仍沿用原目标列裁剪。

沿用全量示例保留与原总像素预算，默认其他Profile仍逐案例发送。仅合并重复图片，不删除连接，不修改正式Agent/公共Schema，不推造新Expected。按用户此前要求不运行验证、测试、打包或模型，实际效果待用户实测。

## 完成状态

以上编辑已完成，本地Profile为2.3.4、manifest v16。同组首条示例附共享整页图，后续示例仍有完整任务和独立答案，通过文字沿用前图；分组顺序按图片首次出现排列。实际任务和示例答案保留原单任务Schema，避免示例批量格式影响当前输出。调用metadata记录completion_example_presentation。

使用原本地命令、--agent-source test --profile zh和新的输出目录/run-id即可。按用户要求未执行验证脚本、测试、类型/lint、打包、真实模型或数据库/Storage操作。正式规则、服务及现有结果保持，模型实际效果待用户实测。
