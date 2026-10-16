# 按用户manifest精简ZH样例

用户手工保留003C01初扫与相关跨页案例，本次以其stage2_cases/stage3_cases为准清理，不扩展或恢复案例。

- 当前1组初扫、5组补全（含用户保留的重复N负例），4张图：003c01、003c31、004c01、080c10。
- 删除未被案例使用的6张图片，以及4份旧初扫expected、4组旧补全task/expected共12份JSON。仅作用于ZH当前examples_wiring/002c目录，原始图纸/其他Profile/已有结果保留。
- 清理manifest顶部失效图片目录、更新描述与manifest v13；Profile版本保持2.1.1，资源checksum变化。README/provenance及两处测试资源引用同步，元数据JSON仍有校验用途。
- 初扫实际请求由5个案例减少为1个；补全仍从现有5例中选1个。Prompt、模型参数、算法和脚本命令不变，不能据此宣称重复生成问题已解决。

只做静态语法、路径、Schema、引用及摘要核对，不运行测试/模型，不写数据库、不发布。复测请用新的目录和run_id，避免将不同资源指纹的产物混在一起。

静态核对通过：1组初扫与5组补全的Pydantic Schema/路径、16项资产及策略/Prompt摘要、剩余文件无孤立引用、两份修改测试文件的Python语法与本次范围diff空白检查。services/agent活动代码中已无已删样例文件引用。
