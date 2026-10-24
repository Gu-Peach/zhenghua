# 本地提取测试副本

2026-10-22当前副本ZH2.7.0：局部只抄录文字块，失败来源连接有限整页复查，目标候选路径门禁及独立整页连通性复核，电压/频率伪端子拦截；起点/原理号和已有终点冻结。代码/案例编辑完成，7项离线用例未运行，未调用真实模型。新目录使用zh_270，见[记录](./changelog/2026-10-22-agent-test-source-recovery.md)。下文为历史版本。

2026-10-22当前副本为ZH2.6.0：初扫同时给出跨页区域框，来源原图宽高各40%窗口按区域批量核读，再索引目标页和整页补全。新增端子特征Prompt及source_marker_verify，冻结起点/原理号/同页终点，无独立locate调用；诊断保存到运行根目录/source-marker-verification/物理页。代码/案例编辑完成，未运行测试或模型，见[记录](./changelog/2026-10-22-agent-test-marker-verification.md)与[方案](./zh-marker-verification-plan.md)。下文是历史版本。

2026-10-22当前副本为ZH2.5.0：按用户最新要求取消source_reference_locate/read，整页初扫按放线段和引用分型确定同页/跨页并冻结；目标整页复扫显式返回最近端子并立即停止。新门禁由segment_trace_rules启用，3图4正例全量展示保持。未运行验证或模型，见[记录](./changelog/2026-10-22-agent-test-segment-two-pass.md)及[设计](./zh-segment-two-pass-plan.md)。下文是历史实验状态。

2026-10-22当前副本为ZH2.4.0：来源箭头/引用区域定位与原始高清图精读后，程序核对地址和唯一业务页，再用完整目标图定向补全；冻结起点与原理号。旧缓存原PDF不可用时靠高清图定位/精读，不凭其他PDF猜测。新增诊断在运行agent/source-references/<页号>/，原命令参数保持、使用新输出目录；未运行验证或模型，见[实施记录](./changelog/2026-10-22-agent-test-source-reference-refinement.md)和[设计](./zh-source-reference-refinement-plan.md)。下文为历史配置。

2026-10-22当前副本为ZH2.3.5：实际目标裁剪宽度扩大到原始整页40%，高为全页，靠近边缘平移保宽；分组示例仍用3张整页图。未运行验证或模型，见[记录](./changelog/2026-10-22-agent-test-zh-crop-width.md)。下文版本为历史状态。

2026-10-22当前副本为ZH2.3.4：补全4条正例按3张目标图分组，003C31只附一份整页图，两条任务和独立答案保留；实际单任务裁剪保持。未运行验证或模型，见[记录](./changelog/2026-10-22-agent-test-zh-grouped-images.md)。下文为历史状态。

2026-10-22最新副本为ZH2.3.3：仅保留003C01整页初扫和4个该来源页跨页正例，删除负例/其他来源页案例，每次补全全部发送，预算不静默删例。目标列裁剪与receiver过滤保持。未运行验证或模型，详见[修改记录](./changelog/2026-10-22-agent-test-zh-all-examples.md)。下文2.3.2/2.3.1是历史状态。

2026-10-22当前副本更新：用户重新调整后的ZH现为本地2.3.2，恢复ZH完整原理号、PageScanData、引用对象及Ir/In/Ie口径，保留当前开启的目标列裁剪；不再把下文2026-10-20的2.3.1整页实验配置视为当前状态。按用户要求本轮未运行任何验证/测试/模型，详见[修改记录](./changelog/2026-10-22-agent-test-zh-rule-alignment.md)。使用现有入口并显式指定`--agent-source test --profile zh`及新输出目录。

2026-10-20，用户已把extraction_agent复制到仓库根`agent_test/extraction_agent`，要求后续本地测试使用该副本，测试ZH整页目标图、初扫原理号与002C03同页样例，不上传数据库。

1. 已完成：入口及隔离基线。开始时正式/测试副本均为ZH2.3.0列裁剪，副本绝对import仍指向`src.agent.extraction_agent`；已记录207个正式源码/资源摘要。复用本轮此前已核对原图/用户标准表的002C03本地快照，不修改正式包或覆盖用户文档改动。
2. 已完成：测试代码/资源切换。仅在本地CLI进程启动、任何提取模块导入前，将`src.agent.extraction_agent`解析至`agent_test/extraction_agent`；其他共享配置、Schema注册和模型Gateway继续复用现有服务库，缺失副本或已混入正式提取模块时停止。两个本地入口的memory_settings固定测试Profile目录，禁数据库/Storage，不通过修改.env或生产包实现切换。测试ZH设completion_view.enabled=false，案例也用整图，保持全页坐标及原有像素预算；新增002C03、line_number/wire_number=null与回指→原理号回退规则，副本调用指令/模型Schema同步。目录整体Git忽略。
3. 已完成：30项相关离线回归通过。新进程核对两个CLI的application、graph、adapter、policy导入均在副本；2初扫/7补全真实图片Fake回放、整图/示例比例/整页坐标/Schema通过，网络禁止。实际CLI预检1来源页/679可用图片、40文件本地包校验和207正式文件摘要核对通过。Ruff、新加载器/PDF入口mypy通过；完整分组脚本10项旧类型问题与HEAD基线相同，未作无关修复。未发布、迁移或重启正式服务，见[交付](./changelog/2026-10-20-local-extraction-test-runtime.md)。

`agent_test/`整体Git忽略，现有本地副本保留。后续clone不含该副本，运行前需自行复制；脚本不能自动复制或静默改回正式版。正式服务的Python加载方式及数据库已发布/冻结规则包保持。

此处“整页”表示不做引用列裁剪，不保证原始像素尺寸：仍遵循输入长边和总像素预算。只切本地测试入口，不改变Worker、Explain重扫或前端规则来源。

## 使用

分组入口默认输出`agent_test/runs/stage2`；建议每次独立试跑指定新目录与run-id：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --profile zh --groups 002.C 003.C 004.C `
  --output-dir agent_test/runs/zh_fullpage_001 --run-id zh-fullpage-001 --allow-real-model
```

新PDF入口相同选择测试实现，参数保持：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_page_workflow_extraction.py `
  "E:\图纸目录\图纸.pdf" --profile zh --max-pdf-pages 0 `
  --output-dir agent_test/runs/pdf_fullpage_001 --run-id pdf-fullpage-001 --allow-real-model
```

这两个命令会实际调用已配置模型，需要用户手动执行；本轮未代跑。启动首行应为`Local test Agent: E:\project\zhenghua_test\agent_test\extraction_agent`。缺目录时按报错自行复制，禁止脚本自动覆盖本地副本。仅导入脚本函数不执行CLI选择，供既有Fake-stage单测使用；任何真实模型执行均再次检查实际代码来源。

相关本地测试在未安装用户忽略副本时跳过该副本的集成场景，缺失/混用保护仍离线可测；原有分组Fake-stage单测显式使用稳定正式样例，不依赖用户私有目录。
