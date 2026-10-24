# agent_test ZH2.7.0来源恢复与目标路径复核

2026-10-22，按用户“基于你说的继续修改”完成本地代码、Prompt、Schema、案例与说明编辑。设计见[来源恢复方案](../zh-source-recovery-plan.md)。未调用真实模型，未执行回归/类型/lint，新增测试代码尚未运行。

## 对应的问题

2.6.0实测63条中33条终点非空，2.5.0为57条中38条。002C03初扫将同页段误报跨页，核读否决后没有恢复同页end；002C06局部可见+01F10/11.1却输出=M前缀；002C11目标相线串到其他回路XD21:1，并把380VAC当起点。以上是既有日志/原图观察，不是本版验收结论。

## 实现

1. 独立原文抄录：核读输入删除initial_raw/initial_signal/initial_path，输出text_blocks、address_block_index、signal_block_index；程序只从选中块取字面地址，模型没有另一个可自行补全工作区的raw字段。原始初扫值保留诊断，仍可能发生视觉识别错误，不能保证逐字准确。
2. 来源恢复：局部核读之后，对无有效核读引用、缺引用/缺框、否决、语法无效且缺end的有效起点连接做整页复查，每批最多8条，candidate_id严格对应。只补同页end或重新定位跨页，已确认起点/原理号/方向/end不改。新跨页引用再核读一次，不循环；合法地址但索引缺页不靠目录猜字。
3. 来源证据：同页恢复要求连续路径从冻结起点坐标到另一端、端子标签与坐标一致，且放线标记/起点身份确认。起点、原理号冲突标复核，不偷偷换针脚。仅清除明确电压/频率伪端子，不根据邻线填起点。
4. 目标复核：补全先给最近端子候选和path_evidence；程序检查身份/连续性声明、最近边界、路径首尾及原理号，结构成立时再独立请求完整目标图复核。复核不接收原候选追线说明或路径，只给冻结任务和候选端子；复核路径必须锚定同一回指并连接候选。失败清空end/nearest_terminal，candidate_end/path_verification保留，并替换错误的肯定性source_note为复核原因。
5. 中继页：当前目标页只有后续延续箭头时保留continuation_references并标待复核，不跨到其他回路补端子、不自动跨多页。
6. 非端子拦截：明确电压/频率字符串（380VAC、24VDC、60Hz等）不作为terminal，XL:2A等针脚保留。正常端子识别仍以图面为准。

新资源connection_review.json控制enabled、source_recheck_enabled、target_check_enabled、batch_size=8、point_tolerance=0.025。目标路径复核要求目标整页，不能同时打开目标裁剪。其他没有该Profile资源的模板不进入新恢复/复核流程。原图40%宽高窗口与原像素预算保持。

## 修改入口

- domain/models：ConnectionPath、TargetPathReview、SourceRechecks、ConnectionReviewRules，以及文字块索引契约。
- infrastructure/document/source_recheck.py、target_review.py：有限来源恢复与候选复核/否决；marker_verification.py：独立文字抄录和initial/recheck窗口命名。
- application/path_evidence.py：几何和端点一致性门禁，不做像素连通性计算。
- infrastructure/zh_vlm_stages.py：连接新操作和各自正例；page_workflow_extraction.py传递取消检查；Graph fingerprint更新隔离旧checkpoint。
- profiles/zh/terminal_identity.py及normalization/validation：电压/频率伪端子拦截；本地Profile2.7.0、manifest20和Prompt同步。

## 诊断与案例

日志stage新增source_connection_recheck、target_path_check；source_marker_verify继续保留。来源目录有初始抄录、整页复查批次输入/结果、source-rechecked-scan及after-source-recheck第二次抄录。cross-page-results保留path_evidence、candidate_end、path_verification、continuation_references。原run目录和正式规则不改。

Few-shot仍只来自原003C01及其目标图：2窗口15条引用改文字块格式；原2条同页XD3连接作为1个恢复正例；原4条终点追加路径、生成4个独立复核正例，3目标图共享。新路径点基于已查看图面标注，未经过用户人工复核；原端点/原理号事实不变，无新增负例或其他来源页案例。

新增agent_test/tests/test_zh270_guards.py共7项离线回归，覆盖省略工作区保持、异常前缀拒绝、电压/针脚区别、同页恢复与冻结、延续箭头不能填端子、已确认终点不覆盖、候选否决；本轮未运行。仅执行JSON资源编写脚本，不执行提取逻辑、打包或真实模型。

## 剩余边界

VLM仍可能把文字或路径看错，第二次复核不等于客观图形连通性证明；点位容差与要求会增加待复核。已冻结但错误的起点/原理号不会自动改写；无有效起点、未初扫出的漏行不通过本恢复流程补造。未支持中继页自动多跳。新步骤增加调用数/耗时，用新zh_270运行目录实测后再判断质量。
