# XMZ 大车卷盘图纸规则

本地Profile为`zh_gantry_reel@0.2.0`，适配器`zh_gantry_reel_native`，资源目录为`prompts/xmz`。保持experimental，不上传或发布。

三份Prompt分别用于页面分类、Stage 2初扫和内部目标图补全。初扫与ZH一致：放线斜杠 → 最近端子/跨页箭头 → 同段箭头定向；图中字段能读到什么就保留什么，未标针脚为空。颜色为空，terminal_strip由程序从实际X排号确定，不套用XA/XD分类。

SH.NO.原标和网格地址使用本模板独立规则：1E→GCR.1/5，1G45H→1G页45列H行；TD 3.a与原理图3A分开。端子报告保留身份，不重复提取。

## 图片样例

- 分类：1A身份正例、TD 3.a非接线页负例。
- 初扫：一张1B来源图，示范选定制动器本页段和ABS跨页段。
- 内部补全：1B来源事实→2A目标图，未标针脚保留部分事实。
- 局部案例只示范指定段，不表示模型只提取这些段；实际扫描处理整页所有符合规则的放线段。
- `stage3_cases`仍是共享加载器的历史键，表示Stage 2内部补全，不是独立Stage 3。

所有expected和task仅使用配套图片可读事实。1E的X0:5/6/7、1G的1F23N～1F28N照录；BRAKE1缺失针脚和绝对值编码器缺失代号/针脚为null。不使用人工表中的X1/X2、XD柜端子、MVCR别名、0261/2401等电缆编号或备用芯。CASE原表和PDF未修改。

manifest保存资源checksum，结构使用共享Pydantic Schema。已删除的sheet-index、field-rules、schema和provenance文件不再作为运行依赖；页标索引由policy读取输入PDF建立。

离线回归入口：`python -m pytest services/agent/tests/unit/test_zh_gantry_reel_profile.py -q`。本轮未运行测试、提取或真实模型，效果待用户验证；导出沿用原生SH.NO.与统一14列。

2026-10-15：主表统一为ZH14列，含色标空列及两端坐标；初扫/补全expected按配套图实际端子符号或接点中心补齐人工目视坐标，未标针脚仍为空，待工程复核。无模型调用或数据库写入。

## 目标局部图

`profiles/zh_gantry_reel/completion_view.json`配置01～48列；目标列左右各11列，全高保留回指、实际端子与较宽的设备描述区。网格很密，因此不照抄ZH的0.95列。缺失/冲突/越界列或不支持布局时回退整页，局部图仍受旧整页像素预算约束。精简任务同时给出原生SH.NO. `drawing_label`与程序索引，模型按原生页标匹配。`signal_name`保留24VDC/ABS等完整线路身份。旧案例在`offline_manifest.json`，运行时只加载`manifest.json`，不删除分类资料。
