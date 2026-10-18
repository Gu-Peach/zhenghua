# 平台提取对齐本地Stage2脚本

按用户要求，平台上传与本地脚本共用请求构造、数据处理和输出字段。运行契约为`stage2-script-aligned-v1`，ZH规则仍选`zh_crop@2.2.1`；未改ZH Prompt、Few-shot、走线/定向补全或复核策略。设计见[计划](../extraction-entry-alignment.md)。

## 修改

- `application/extraction_contract.py`保存脚本原有的禁色标前缀、幂等追加、color=null后处理、页面身份构造及过滤前诊断。平台与脚本均经共享`ExtractionStageGraphClient`，脚本不再有专属scan_page逻辑。
- 平台从已分类索引补全DrawingPageInput业务工作区、页号、Object Loc及非接线标志，索引按mtime/大小缓存；保留分类前的渲染图片回退。物理页始终使用PDF页号。
- 共享模型Gateway构造，统一模型地址、超时及重试配置；仍服从各次执行显式选择的模型设置，不新增模型调用或调整温度。
- `domain/table_output.output_fields`同时驱动脚本14列和平台PublishedRow业务字段，统一元件device→location回退、原理号、端子、当前值、备注及坐标；色标为空。API字符串字段仅做原有文本传输转换，坐标仍为对象，XLSX坐标格仍为JSON文本。持久化身份、项目隔离和逐页事务不变，无迁移或前端DTO变更。
- 模型请求增加可对照的request_fingerprint和运行契约版本；脚本调用日志也记录系统Prompt摘要。指纹采用旧脚本的模型/消息/温度/max_tokens/JSON模式/思考开关计算方式，不存API key、授权头或图片data URL。不同任务的task_id可以不同，跨页请求比对需使用相同任务上下文。
- scan_diagnostics保存解析后、接收端过滤前的连接数及保留数，区分no_connections、receivers_only、sources_retained和skipped。此字段由程序计算，不进入VLM的JSON Schema、不作为模型可决定的业务值；平台快照/指标与本地JSON均保留。
- 修复DrawingReference.target_column最小值为0，合法`=098.M/1.0`可通过。页号/PDF物理页仍从1开始；ABB的0列由其独立策略标无效，XMZ保留1～48列范围。
- 新契约写入Worker配置和本地工作流指纹；旧任务不自动换规则或改写成功页。旧配置不匹配时不混用缓存；用户本次以新上传验证。

## 已核对

全程无付费模型调用、数据库写入、旧结果覆盖、Storage上传或用户服务启停。

- 对003C02、004C04/05/06离线执行实际请求构造前缀，平台新冻结包与脚本的页面元数据、初扫消息及请求指纹逐项一致。为核对历史，仅在内存将Schema的0列下限恢复成原来的1后，四份完整请求指纹均精确命中stage2-crop-003的历史缓存；除此没有文本/图片差异。
- 对四页已有的14个可解析跨页任务，使用同一任务上下文，两入口构造的目标局部图消息完全一致；未发送模型请求。
- 154条历史记录的表格值逐格保持，154条平台业务投影与脚本14列语义一致，包括未知值、备注、元件回退和坐标。
- 0列接受、负列/零页号拒绝、ABB0列无效及三种诊断分类通过离线数据核对。打包资源/Schema/摘要与两CLI帮助检查通过；15份相关文件Ruff与AST检查通过。
- 13份源码严格mypy仍有18条既有Graph/持久化问题，与独立HEAD源码基线对照无新增；未修无关类型问题。明细在被忽略的`.runtime/extraction-entry-alignment`。
- 已补充请求一致性、冻结包/本地资源、接收端过滤诊断、输出映射和0列边界回归文件；按用户既有要求，未执行pytest、Fake VLM或真实模型测试。离线一致性不等于实际模型精度验收。

## 用户测试

先重启实际执行提取的Worker（若由8100内置Worker执行则重启该服务），启动日志应出现`contract=stage2-script-aligned-v1`。再新上传PDF，选择“振华跨页局部高清（本地实验）·2.2.1”。新任务configuration/模型调用metadata同样记录该契约。

前端页面与API不需要因本次改动重新构建。旧任务与其322条已保存结果保持，不用旧任务的普通重试来验证新请求。平台仍冻结任务规则包和逐页落库，冻结包与本地资源进入的是同一套提取实现。
