# XMZ 大车卷盘图纸规则

本地Profile为`zh_gantry_reel@0.1.1`，适配器`zh_gantry_reel_native`，资源目录为`prompts/xmz`。保持experimental，不上传或发布。

三份Prompt分别用于页面分类、Stage 2初扫和内部双图补全。初扫与ZH一致：放线斜杠 → 最近端子/跨页箭头 → 同段箭头定向；图中字段能读到什么就保留什么，未标针脚为空。颜色为空，terminal_strip由程序从实际X排号确定，不套用XA/XD分类。

SH.NO.原标和网格地址使用本模板独立规则：1E→GCR.1/5，1G45H→1G页45列H行；TD 3.a与原理图3A分开。端子报告保留身份，不重复提取。

## 图片样例

- 分类：1A身份正例、TD 3.a非接线页负例。
- 初扫：1E电机放线；1B选定制动器/ABS段；1G选定编码器段；2A选定PN2出页段；TD空连接负例。
- 内部补全：2A→1F明确接口正例；1B→2A未标针脚的部分补全。
- 局部案例只示范指定段，不表示模型只提取这些段；实际扫描处理整页所有符合规则的放线段。
- `stage3_cases`仍是共享加载器的历史键，表示Stage 2内部补全，不是独立Stage 3。

所有expected和task仅使用配套图片可读事实。1E的X0:5/6/7、1G的1F23N～1F28N照录；BRAKE1缺失针脚和绝对值编码器缺失代号/针脚为null。不使用人工表中的X1/X2、XD柜端子、MVCR别名、0261/2401等电缆编号或备用芯。CASE原表和PDF未修改。

manifest保存资源checksum，结构使用共享Pydantic Schema。已删除的sheet-index、field-rules、schema和provenance文件不再作为运行依赖；页标索引由policy读取输入PDF建立。

离线回归入口：`python -m pytest services/agent/tests/unit/test_zh_gantry_reel_profile.py -q`。本轮未运行测试、提取或真实模型，效果待用户验证；通用导出的原始SH.NO.展示仍是后续任务。
