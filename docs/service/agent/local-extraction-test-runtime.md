# 本地提取测试副本

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
