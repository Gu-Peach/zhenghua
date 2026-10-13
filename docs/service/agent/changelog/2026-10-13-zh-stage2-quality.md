# ZH Stage 2 质量修正（本地2.0.1）

旧002.C/002.M试跑有121条；人工核对至少25条方向、端点或引用归属错误，其中24条被resolved、1条被complete误当成功。旧状态统计为31 needs_review、4 needs_reference；完成状态不能作为字段准确率。

本次修改：

- ZH Prompt注入实时Pydantic JSON Schema，显式要求endpoint_role/direction_basis，并修正原示例缺字段。角色/依据缺失降级unknown/needs_review；明确receiver过滤，不根据XD前缀换向。旧未知方向可读事实继续保留并复核。
- 初扫强调逐根连续追线、局部柜体、完整设备/端子排；区分真实针脚、PLC通道地址、电位名和器件定义引用。同页端点优先，不借相邻动力/辅助触点地址。
- 仅明确来源分支逐条输出；未确认终点的去重键纳入其引用，保留同源同号两分支。仍对单条未拆分多目标冲突留空复核。
- 原始引用地址优先于模型派生地址；支持局部5.1、/21.1、=.M/=M相对功能、完整跨功能地址。纠正后重新查物理页，不沿用旧错误页；单个raw混入多个地址不选第一个。
- 缺端子身份/针脚不能标成功；识别到PLC地址或电位名冒充端子时清空该针脚字段、保留原值诊断并needs_review。端子类型不设白名单，非XD端点继续允许。
- 双图补全需source_note中的目标实线证据，缺证据保留可读字段并复核；Prompt增加FO2→1R、变压器二次侧→XL三相、FC112实际供电输出与辅助触点区分。
- 新增C02、M03运行时真实图片Few-shot及FO2双图；C05/M01局部固定字段集用于离线回归，避免把局部答案说成整页答案。manifest v3、ZH2.0.1及资源/校验器checksum同步。

公共Schema/API没有改变，校验过domain-schema.sha256。ABB/大车卷盘显式关闭本次ZH证据扩展，保留各自规则；大车卷盘策略校验和因兼容开关同步，语义不变。共有去重修正有完整Fake Graph/保存恢复用例。

验证：40项离线冒烟（其中新增质量用例26项）、7项原生模型接口/大车卷盘资源边界回归；资源路径/字段/摘要、Ruff与修改源码strict mypy。真实图片是资产输入，模型响应来自Fake，没有执行真实视觉准确率评测。

没有数据库/Storage请求或写入、migration部署、远端包发布、服务重启、环境修改、提交或付费模型调用。旧docs/test/run_stage2结果原样保留；真实2.0.1提取质量仍待显式新目录试跑，不能根据离线通过宣称已提升准确率。

离线命令：

```powershell
$env:PYTHONPATH="E:/project/zhenghua_test/services/agent/src"
.\.venv\Scripts\python.exe -m pytest services/agent/tests/smoke `
  services/agent/tests/unit/test_native_vlm_stages.py `
  services/agent/tests/unit/test_zh_gantry_reel_profile.py -q
```
