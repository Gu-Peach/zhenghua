# agent_test ZH来源页正例全量发送

## 本轮范围与执行方案

按用户2026-10-22要求，仅在agent_test修改ZH。这里“本页”指截图中的003.C/1来源页，跨页目标图仍是补全必要输入。保留该来源页的四个现有正例：XA:8到080C10 XD10:1、XA:11到003C31 XD10:1、右侧N-BAR到004C01 XD10:4、中间N-BAR到003C31 N-BAR。不从现有代表性案例推造未核对的其余端子Expected。

执行顺序：先清理manifest及仅被移除案例使用的资产，再用本地manifest元数据声明全量补全示例，适配器按清单顺序发送全部正例；本地图像预算保留整组示例，可缩小但不静默删除。默认单例排名保持，ABB/其他规则不启用全量模式；不更改共享Profile Schema或正式Agent。

负例repeated_n_requires_source_identity及来源004C02、004C09的两例移出本地资源集；003C01原图作为初扫输入保留。运行仍逐连接补全当前任务，全部示例只作为上下文，不把示例答案当成当前任务输出或替代整页实际识别。

## 完成状态与使用

本地ZH标记2.3.3，manifest v15，以上编辑已完成。初扫仍展示原整页Expected全部连接，补全发送4个现有来源页正例，按原顺序；删除3组案例的6份JSON与独占005C01图片，保留其他原图/Expected事实。删除样例不取消未知字段留空的规则。

全量模式由本地manifest的completion_example_selection=all控制，不扩展公共Profile Schema；缺省模式仍是ranked。预算仍优先实际输入，4例全部保留，紧张时允许示例低于原最小长边，预算无法容纳时明确失败。模型调用metadata记录completion_example_selection与vision_preserve_all_examples，可区分全量/默认模式。

沿用原命令，只需使用新的输出目录/run-id；本地Profile README给出002.C/003.C/004.C命令，参数不变。按用户此前要求未运行验证、测试、类型/lint、打包或模型，实际质量与示例清晰度待用户实测。正式Profile/服务/数据库和既有结果不改，继承的provenance仍是历史来源，不代表本轮验收。
