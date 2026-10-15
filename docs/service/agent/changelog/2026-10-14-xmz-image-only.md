# XMZ本地规则与图像事实样例对齐

资源目录沿用用户新命名`prompts/xmz`，本地Profile升为`zh_gantry_reel@0.1.1`，key和adapter不改，仍experimental。

## 修改

- Profile/rules改用实际资源路径，去除用户已删除的sheet-index、field-rules和schema依赖；页标仍由policy读取输入PDF建立，结构化响应使用共享Pydantic模型。
- 初扫对齐ZH放线斜杠优先、最近端子停止、同段箭头定向；补全在目标图第一个实际端子停止。保留独立SH.NO.与网格引用规则、电流依据约束，不借用人工表。
- 模型terminal_strip=null，程序优先使用起点、其次终点实际X排号；都无实际排号时为空。颜色为空。适配器同步指令与共享Schema注入。
- 分类2组、初扫5组、补全2组图片案例。初扫包含1E电机、1B局部制动器/ABS、1G局部编码器、2A局部PN2及TD负例；局部案例不限制真实整页扫描范围。
- 全部expected/task以图片为依据：保留X0:5/6/7、重复1E09R和1G图中1F前缀；BRAKE1无针脚号、绝对值编码器无代号/针脚时置空。无放线斜杠的CLIQ不作为初扫记录；跨页正例为带斜杠的2A B1:P2→1F CU320 X150:P1，新增目标页真实图片。
- manifest同步图片、task、expected路径并保存checksum；回归文件不再依赖已删除诊断资料，README和版本记录同步。

## 验证与边界

只做静态资源路径/JSON/Pydantic Schema/checksum/Python语法与只读Profile绑定核对，不运行pytest、Graph或真实模型，不写数据库或上传/发布，不修改用户源PDF、XLSX或已有结果。真实识别效果待用户验证；原始SH.NO.通用导出展示仍是后续范围。
