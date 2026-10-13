# Stage 2 逐页闭环提取

2026-10-13，分支 `codex/stage2-page-workflow`。设计见 [ADR-0014](../../../adr/0014-stage2-page-extraction-workflow.md)。

## 改动

- 独立 Stage 2 入口：`services/agent/src/agent_service/graphs/document_extraction/page_extraction.py`。每页执行初扫、引用规划、来源/目标双图定向补全、校验与保存，再进入下一页。主 Agent 可包装此入口为工具/子 Agent；初扫 `run_page_scan` 是内部操作。
- 删除 `CrossPageResolverAgent`、独立 `cross_page_completion` 子图及文档全局 Stage 3 调度。完整运行、进度事件、局部纠错改为 Stage 2 内部补全。历史阶段/请求/资源标识保留以读取既有数据，不是新阶段。
- 文档级入口迁为 `application/page_workflow_extraction.py::run_page_workflow_extraction`，CLI 改名 `scripts/run_page_workflow_extraction.py`；真实调用必须显式 `--allow-real-model`。
- 本地完成页使用唯一临时文件和原子替换，保存成功后才推进；指纹包含运行/Profile、配置和页面内容，恢复跳过完成页。数据库适配器区分原始模型缓存和完成页 StageItem，内部补全也属于 PAGE_SCAN。
- 缺失/外部目标、未补全的回指来源和模糊终点留 null/needs_review，保存原因，不递归扩张，不阻塞后续页。正常目标页回指用于匹配，不判为循环；配置/权限/保存失败仍终止。真实 SQL/Storage 未运行。
- ZH 2.0.0 移除 XA/XD 白名单、强制换向及端子排清空。箭头相对端子决定来源，接收端不创建记录；无箭头由模型按图中证据判断，不确定保留复核。实际端子字段保留，明确端子排值优先，已知映射作为后备，无映射/冲突留空。
- 不再自动给 PE 填色标或未确认终点；不把业务代号、颜色、缺失电流编造为图中值。诊断 XLSX 第三列改为端子排，行按来源页处理/页内视觉顺序保留。来源页归属使用明确物理页，不因目标页更早而换页；证据的 source/target 与归属一致。
- C01 正例、C03 接收端局部负例和 C01→C02 双图案例纳入 manifest v2；旧白名单 expected 归档。新 expected 已目视核对，但仍需工程人员确认/真实模型字段级验收，不宣称准确率已通过。
- 内部领域 Schema 升为 V5，追加 source_page、endpoint_role/direction_basis 并更新 checksum。无新增外部 HTTP 路由，历史枚举值兼容。
- 新增未部署的 migration `supabase/migrations/20261013010000_stage2_page_workflow.sql`：按冻结 `page_extraction_v2` 选择阶段前驱，并校验封存扫描事实与逐页 canonical item 相同；旧数据库输入保留原阶段历史。代码不恢复旧三阶段 run，新运行才使用新工作流。新 migration 未执行，不修改已应用迁移。

## 验证与边界

用户要求本轮只跑冒烟。执行：

```powershell
.\.venv\Scripts\python.exe -m pytest services/agent/tests/smoke/test_stage2_page_workflow.py -q
```

10 项离线冒烟通过：逐页调用顺序/双图、非 XD 起点及接收端排除、未知/回指空值、逐页保存失败停止、缓存恢复、实际端子优先与 PE 空值、内存 repository 的完成页/模型缓存区分、纠错内部补全、来源页/证据归属、配置失败不掩盖、同页同电缆多组的连接 ID 不冲突。测试禁用 HTTP 请求；全部使用 Fake VLM、临时本地文件或模拟 repository。

修改 Python 文件 Ruff 与语法检查通过。未运行全量测试、真实 VLM、真实图片字段级固定回归、数据库迁移/集成或浏览器测试；未连接/写入真实数据库、发布远端规则、重绑已有项目或重启服务。

当前每页保存的是结构化完成页事实；业务结果版本仍由 Server 在运行结束后原子提交，尚不提供工作台逐页增量发布。数据库运行需后续授权部署 migration 和 ZH 2.0.0 资源包；现有运行服务及其远端旧规则保持原状态。
