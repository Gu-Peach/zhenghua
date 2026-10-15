# ZH2.0.4：003C01样例与端子图片坐标

## 样例与清理

- 初扫manifest中的c03_receivers_only替换为003c01_marked_segments，使用用户提供的003c01.png及完整expected：15条跨页放线段、2条无直接箭头的同页XD3段（方向待复核）。跨页从斜杠上侧最近XA/XD10端子出发，不输出上方无标记的断路器到端子连接。
- 原两组跨页案例替换为003C01 XA:8→080C10 XD10:1，以及003C01 FC13组N-BAR→004C01 XD10:4；分别使用原理号/对应引用区分线路。目标回指+01F11.1按2.0.3元件优先级完善起点元件，不改变来源端子和坐标。
- 仅清理ZH样例目录的7张独占旧图、旧接收expected及4份旧跨页expected/task。保留原图docs/test/pages、其他Profile和旧结果。manifest v8仅列运行时使用的7张图，仍为5组初扫/2组内部补全。

## 坐标契约及输出

新增可选端点terminal_coordinates={x,y,pdf_page_number}，x/y为实际端子符号/连接点中心相对整张图片的归一化坐标（0到1，左上角为原点），不使用文字、斜杠、箭头坐标。坐标未知为null；缩放图保持归一化位置。页号由程序绑定实际来源/目标输入图，避免模型用来源页替代目标页。

WireRecord新增start_terminal_coordinates/end_terminal_coordinates；扫描、补全、扁平化、JSON及普通XLSX诊断导出保留。坐标是图像证据，不参加连接身份去重或跨页终点冲突判定。source_component仅完善元件元数据，起点端子/坐标保持冻结。

本地run_stage2_groups.py与Node导出器在原12列之后追加起点端子坐标、终点端子坐标，共14列，坐标对象以JSON字符串保存。原1641.xlsx仍作为12列样式参考，不修改该文件；色标仍为空。公共HTTP路由与数据库Schema未调整，现有业务表/前端坐标展示不在本次范围。

ZH Profile升2.0.4，Prompt/调用文字/运行时Schema说明、expected/任务、资源摘要同步。新增或更新坐标范围/物理页绑定、来源坐标冻结、扁平记录/14列输出与资源包路径的回归用例。

## 验证

仅静态核对通过：5组初扫/2组补全的manifest路径、Pydantic Schema和坐标页号，7张图片引用集合，13份修改Python语法，Node导出器语法，ZH2.0.4只读注册及资源checksum、git diff --check。样例坐标是人工读图标注的符号中心，实际VLM定位效果尚未验证。

遵照用户此前自行测试要求，未运行pytest/冒烟、真实模型或提取脚本，未生成新XLSX；不写数据库/Storage、不发布/重绑规则、不启动/重启服务，不覆盖旧结果。仓库其他未提交改动保留。
