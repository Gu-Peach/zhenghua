# ZH expected字段同步

按用户确认，将当前运行时样例的三处旧写法与ZH2.0.2 Prompt同步：

- C01：XD1端点补terminal_board=XD1；L1/L2/L3与FO1～12完整写成XD1:L1、XD1:FO1等；PE按现有约定保留。W1作为设备，不补造实际端子排。
- C02：K2/K3的name分别填写原图MAIN TRANSFORMER FEEDER和AUXILIARY TRANSFORMER FEEDER，不再留空。
- FO2补全：device=-TF41、terminal=1R保持，terminal_board=null，不用设备代号代替排号。

保持初扫5组/补全2组、连接条数、方向、引用和Prompt不变；本地ZH仍2.0.2，manifest升v6，三个expected的资源摘要同步。只读核对后的文件修改，不运行测试/提取/真实模型、不写数据库/Storage或发布，不覆盖旧XLSX。
