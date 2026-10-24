# zh_test 当前样本：006M01 → 006C01（待用户校对）

样图来自用户PDF物理第2页006.M/1（+01F11.3）与物理第3页006.C/1（+01F26），保留原红框和标注。当前manifest v15：初扫1例、对应目标图补全6例；旧索引存入offline_manifest.json，旧文件保留但不注入。

| 截图芯号（仅参考） | 原理号 | 起点（+01F11.3） | 终点（+01F26） | 备注 |
| --- | --- | --- | --- | --- |
| 1 | 003G0121 | XD3:3 | X3:3 | 24VDC+ |
| 2 | 006M0151 | XD3:112 | X3:6 | AIM1 SW Feedback |
| 3 | 003G0121 | XD3:30 | X3:4 | 24VDC+ |
| 4 | 006M0152 | XD3:113 | X3:1 | Main Contact NC |
| 5 | 003G0121 | XD3:30 | X3:5 | 24VDC+ |
| 6 | 006M0153 | XD3:114 | X3:2 | Main Contact NO |

- 初扫图片为images/006m01_source.png，答案为stage2/006m01.expected.json；end=null，保留来源端子及目标引用。
- 补全图片为images/006c01_target.png；六组task/expected分别在completion/。同号003G0121按AIM1_X3_3/4/5信号区分，不能混为一条。
- 起终点按用户截图冻结为006M01的XD3→006C01的X3，反馈箭头不用于交换用户已确认的线表方向。该已知条件写入案例标题和direction_basis，没有修改通用Prompt或代码。
- reference_pairs.json保留截图电缆0272、柜名、芯号、SPARE及PE供校对，不注入模型。运行样例wire_number/core_number及不可见柜名保持null；device按图框为+01F11.3和+01F26。
- 两张样图没有足够接点依据为备用芯/PE生成独立扫描记录或坐标，因此不补造；端子坐标为人工读图近似整图坐标，物理页使用本PDF的2/3，待校对。
- 本轮只更新zh_test样本及分类样例，未改Profile绑定、提取逻辑或数据库，没有运行测试、提取或模型调用。

## 以下为复制前的历史样例说明，不参与当前manifest

# ZH 2.3.0：003C01及重复N线图像样例

当前入口为manifest.json v14，保留用户确认的1组初扫、7组内部补全/负例。历史键stage3_cases仅供加载兼容，不代表独立Stage3。本目录是正式zh2.3.0的唯一样例维护来源，完整保留已验证zh_crop2.2.1的图像和Expected事实。

## 初扫

003c01_marked_segments使用003c01.png及stage2/003c01.expected.json：15条跨页放线来源段、2条同页方向待复核段。按放线斜杠读取直接端子，保留电流证据和端子坐标；不穿过端子重复输出上方断路器段。

## 内部补全

- c01_xa8_to_080c10_xd10_1：003C01到080C10，XA:8对应XD10:1。
- c01_xa11_to_003c31_xd10_1：003C01中间FC12组到003C31，XA:11对应XD10:1。
- c01_nbar_to_004c01_xd10_4：003C01右侧FC13组N线到004C01，N-BAR对应XD10:4。
- repeated_n_requires_source_identity：用户保留的003C01重复N原理号负例，来源身份不足时终点留空复核。
- c01_nbar_to_003c31_nbar：003C01中间FC12组N线到003C31，终点为独立N-BAR，不套相邻XD10相线排号。
- c02_fc11_n_to_005c01_x21_5：来源004C02的-FC11_N对应X21:5。
- c09_lcm_n_to_005c01_x2_10：来源004C09的-LCM_FC50_N对应X2:10，与同页另一条N线区分。

所有补全task使用上下文v2，不包含起点完整端子、坐标或方向描述；原值留在state。只传目标图与来源业务身份、元件元数据、原理号、信号/引用、电流。补全每次仍从这7例中选择1例。初扫只发送003C01这1例。

## 资源与边界

保留5张实际使用图片：003c01.png、003c31.png、004c01.png、005c01.png、080c10.png。当前来源摘要由profiles/zh/completion_view.provenance.json统一维护。端子坐标为实际接点在整图的归一化x/y及本端PDF物理页；手工expected用于定位示例，未知值仍为空。

2026-10-19清理源码重复，将正式已验证资源从profiles/zh/resources归回本目录；资源事实不改。不删除docs/test/pages原图、其他Profile或既有测试结果，不改变工作流和脚本参数。仅静态/打包核对，不运行测试、模型或数据库操作。
