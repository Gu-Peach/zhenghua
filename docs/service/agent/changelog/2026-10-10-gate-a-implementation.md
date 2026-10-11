# Gate A 实施与验证记录

日期：2026-10-10。**Gate A 已通过；Gate B 未实施**。真实模型调用：无。

## 已接入

- 新 `domain/models/stage_persistence.py` 和提交/清单/RunLease/receipt 契约；Python/PostgreSQL canonical JSON、输入/结果/记录摘要分别校验。
- `SupabaseStageRepository`、任务级 ContextVar fencing token；新协议 FULL_EXTRACTION 由正式 Supabase app 创建，旧 run/旧测试脚本保留 protocol 1。
- 公共文档 Graph 在每阶段 `await` 提交并重新从数据库加载；保存模型逐项缓存、不可变阶段清单、Planning connection 覆盖集合；本地 JSON 不再是新协议恢复来源。
- 页面图片上传私有 Storage，下载验证 checksum；新 Worker/新空运行目录能用数据库快照重建状态，CPU 渲染移到线程以便续租。
- Worker 原子接管过期 RUNNING lease、续租、条件 ack 和失败退避；旧非 fenced mutation 被数据库 trigger 拒绝。
- 最终 Proposal 复用既有线表 RPC；增加 durable receipt 和原子 finalize，结果已提交时只补收尾，不重跑模型/分配版本。
- Stage 1 未发布分类留在 Artifact，完整封存后按项目 epoch 原子发布树；新协议工作区/图纸采用 run-scoped UUID 与 snapshot provenance，旧元数据不被重提取覆盖，最终映射使用本 run 快照。

## Migration

本地 `supabase_db_zhenghua_test` 已按顺序事务应用并登记 `20261010000000` 至 `20261010100000` 共十一份追加迁移。后续 SQL 修正均用新 migration，不改写已应用文件。新列/索引/RPC 与历史项目 BEFORE DELETE 聚合清理已做兼容修正；未操作其他项目容器、未重启 Agent/数据库服务。

`verify_gate_a_migrations.py` 已在两个 UUID 临时数据库执行全部 21 份 migration，分别覆盖空 public 库和合成旧 `wiring_tables` 数据快照；两条路径通过，临时库已清理。测试使用 Supabase prerequisite schema fixture，不假称它替代了真实 Auth/Storage；HTTP/Stage 验证使用真实本地 Supabase。

## 验证结果与限制

真实 Supabase + Fake VLM 共 10 场景分批通过：正常非空提取，Stage 1/2/3 中断恢复，结果提交后 finalize 前/后中断，缺页封存与结果冲突，项目树 epoch 竞争，暂时失败重排与取消，以及两个独立 Python Worker 进程的空目录恢复。已提交模型项不重复执行；旧 Worker 的 fail/renew/save/event/artifact/result/finalize/ack 被拒绝；非空线表验证起点、跨页终点、1000 起线号与唯一完成事件/receipt。

开发中遇到 PostgREST 连接池超时，拒绝旧租约改用永久 PT409 业务冲突，不再使用可重试的 40001；仅回收匹配 Gate A 函数名且事务已中止的测试连接，未重启服务。合成残留项目按 UUID、测试名称和 `example.invalid` owner 三重核对并清理私有对象及项目，不删除业务数据。

默认离线回归：105 passed，10 个真实库用例默认 skip。strict mypy：151 源文件通过；Ruff、compileall、diff --check 通过。领域 Schema checksum：`sha256:e7563577b531403060ab0bec0cb59a2e876b5fae04feede99b0b3597d33c1591`。22 个 Gate A RPC/helper 的 anon/authenticated 执行权限检查均未放开。

限制：本轮仅以合成图纸/Fake VLM 验证持久化机制，不替代 ZH 真实图片字段级基线或真实模型费用/准确率评测。长期聊天记忆、Gate B 上传/确认/纯 HTTP 用户链路与 Web 代理未实施。现有电压字段回退的业务含义风险仍保留，未顺手改 Profile 算法。

## 显式验证命令

```powershell
$env:PYTHONPATH="services/agent/src"
$env:AGENT_TEST_REAL_SUPABASE="true"
.\.venv\Scripts\python.exe -m pytest services/agent/tests/integration/test_gate_a_real_supabase.py -q
.\.venv\Scripts\python.exe services/agent/scripts/verify_gate_a_migrations.py
```

测试只创建并清理独立 UUID 的合成项目、用户和对象；异常残留可用 `scripts/cleanup_gate_a_tests.py <明确测试项目UUID>` 逐项三重核对并清理，不接受任意业务项目。请不要并发运行多个同一队列的故障测试进程。内部 `run_gate_a_fake_worker.py` 仅用于机制的进程隔离回归，不是用户验收客户端；后续 Gate B 客户端仍只能发 HTTP/用户输入。
