# ABB / XMZ 提取结构对齐

ABB本地版本更新为1.2.0，XMZ规则键`zh_gantry_reel`更新为0.2.0（保持experimental）。按用户要求，提取采用ZH已验证的“初扫当前页→冻结事实→目标局部图补全→整页坐标输出”。分页Prompt/分类案例、ZH业务规则不改，不发布远端规则或操作数据库。设计见[执行方案](../abb-xmz-completion-alignment.md)。

## 实现与案例

- 纯裁剪/精简任务模块移到`infrastructure/document/completion_view.py`、`completion_context.py`；原`profiles/zh`导入保留兼容入口。ZH算法除支持更宽的配置范围外逐字保留，新增原生页标为可选字段，ZH请求不发送该空字段。
- ABB独立配置1～6列、左右各0.95列；XMZ配置01～48列、左右各11列，避免细密网格切掉设备框/描述。保留全高回指；列无效/冲突或布局不支持时回退整页，不增加模型定位或补全轮次。
- 跨页仅发送目标图、来源/目标业务页、来源元件元数据、原理号、signal_name、引用和电流。不传来源图片、针脚、坐标或方向文字；XMZ适配器还原原生SH.NO.到drawing_label，公共Graph不增加模板分支。
- ABB初扫只加载一张205图/一个案例（合并已核对Q3本页和Q4跨页段），补全只加载对应241目标页；XMZ初扫只加载一张1B图，补全对应2A编码器。均为指定段示范，不宣称整页穷举。旧多案例保留在offline_manifest.json及原资产中，不进入模型请求。
- 1B→2A样例接点未标物理针脚，终点terminal/coordinates仍空；来源1B38R与目标1B39T标注差异在uncertainties明示，不能复制起点针脚。未选2A→1F作为局部示范，因为CU320名称远离接口，窄裁剪会切掉名称。
- 每次补全必须明确end或null，并提供source_note/uncertainties依据；空对象复用原有最多两次Schema尝试。保留起点与已有电流，无法确认留空并继续后续任务，不恢复独立Stage3。
- 样例临时裁剪并转换expected坐标；已知端点不在范围内则该案例回退整页。原图/人工坐标文件不变，JSON/XLSX仍为整页归一化坐标、14列。

## 验证

7个相关源码strict mypy通过；11份相关源码/回归文件Ruff、13份AST与git diff检查通过。四个主要Profile绑定、活动案例Pydantic Schema/路径/摘要、代码provenance共77摘要已静态核对；ABB/XMZ分页Prompt和分类案例、ZH Prompt/规则/案例60份与HEAD内容逐字节对照，另5份本地ZH裁剪图片与HEAD provenance记录摘要对照。旧ZH裁剪provenance只更新共享机制代码摘要，版本/图框配置不变。

离线裁剪预览位于`docs/test/profile_alignment_previews`（忽略，不提交）：ABB目标470×1236=580,920像素，原整图允许2,161,764；XMZ目标1385×2140=2,963,900像素，原整图2048px允许2,965,504。目视确认所需回指/端点或设备区域保留，ABB已知端子坐标往返误差小于1e-12；XMZ未标针脚仍无坐标。

PDF/拆页CLI的--help加载通过，测试命令不变：ABB用`--profile abb`，XMZ用`--profile zh_gantry_reel`，应换输出目录和run-id，避免混用旧Profile指纹。CLI沿用内存/本地文件模式。

按用户既有要求，只补充和同步离线回归文件，未运行pytest、Fake VLM或真实模型，未覆盖旧结果、写业务数据库、上传规则或启停服务。裁剪不能修复错误引用或保证图外字段可读，实际精度/运行耗时由用户新目录复测。
