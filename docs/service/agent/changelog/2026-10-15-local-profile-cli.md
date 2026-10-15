# 本地测试CLI切换规则与PDF

当前两个本地入口原先固定ZH：分组脚本绑定zh并直接构造ZhExtractionPolicy，PDF脚本的--profile只有zh选项。本次按用户切换规则测试其他PDF的需求，增加选择本地Profile key和模型的能力，复用已有adapter/策略注册，不改提取算法。

PDF入口负责拆页、分类与逐页提取；已拆页入口继续读取用户指定图片目录和对应索引。两者均使用内存持久化、移除数据库凭据、关闭远端包和inline worker，不上传或调用业务API。选中的Profile必须有效，其他模板缺失不阻塞本地指定规则；显式指定实验Profile表示手工选择该模板。

已完成：两个脚本支持--profile/--model；分组入口按adapter解析既有策略，PDF入口复用本地内存设置和规则加载，入口加载顺序已调整。保留load_local_zh_profile兼容调用；现有ZH默认参数不变，PDF仍须--allow-real-model。

静态检查通过：两个--help独立运行，ZH2.0.5/ABB1.1.2/XMZ0.1.1只读绑定到对应adapter及policy，内存/checkpoint/远端包禁用配置核对，3份Python语法及资源摘要同步。新增CLI参数及非默认Profile选择的回归用例但按用户此前要求未运行pytest/冒烟。没有实际读取PDF提取、调用模型或数据库、生成XLSX，原结果和用户未提交改动保留。
