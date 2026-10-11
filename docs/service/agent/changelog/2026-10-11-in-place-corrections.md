# 原位纠错：稳定 ID 与审计

日期：2026-10-11。用户明确要求覆盖当前记录，避免局部修改克隆整份结果。[ADR-0010](../../../adr/0010-in-place-confirmed-corrections.md)覆盖此前局部纠错创建新快照的约定。

## 实现

- 直接答案、Stage 2 同页重新识别、Stage 2→Stage 3 跨页重识别最终仍生成 proposal；确认后统一调用 `apply_confirmed_result_patch`，原位更新目标连接。
- 保持 connection/unit/evidence ID、result_version_id、线号和来源关系；不复制全部结果，不修改其他连接。
- `result_versions.version` 为完整提取代次，新增 `revision` 为代次内修订；proposal 冻结 base revision，RPC 事务核验权限、Profile、当前代次、revision、record_version 和 before 值。
- 新 RPC 仅 service-role 执行；批次任一项无权限/过期/越界即整体回滚。feedback before/after 和 proposal receipt 与更新一起提交。重复确认先读 receipt，不递增 revision、不创建重复审计。
- 内存 repository 同步原位语义；业务分页增加 revision，确认 receipt 增加 update_mode/result_revision/updated_connection_ids。领域契约 V3 与 Schema 快照同步。
- 搜索无指定历史版本时，以项目真正的最新代次过滤，避免当前端子变更后误命中旧历史行。
- 旧已提交 proposal 的 snapshot receipt 仍可幂等读取；缺少 base revision 的旧未提交 proposal 需要重新生成。完整 PDF 提取仍创建新代次，不属于此次局部覆盖范围。

## 验证与部署

17 项相关离线测试、strict mypy/Ruff 通过。真实本地数据库使用生成的合成项目/用户，在事务内验证稳定 ID、记录数不增加、revision、receipt 重放、越权/过期拒绝、第二项失败时第一项回滚；全量 rollback，不写入 test0。

`20261011020000_in_place_result_patches.sql` 已事务应用并登记，PostgREST Schema 已重载。anon/authenticated 不可执行新 RPC，service-role 可执行。test0 三个旧代次及 36 条历史连接保留，原字段值/ID 不变；最新代次 3 的 revision 初始为 1，当前连接为 `7d55952a-1f10-4c0c-a4ae-e02c579b10a8`。

服务没有停止/重启，用户需重新加载 Agent API/Worker 才会使用新提交代码。新测试应从当前这条连接注错，确认后在同一 ID 查看正确值，代次仍为 3、revision 变为 2。不再查找新连接 ID。

## 边界

- 旧版本没有自动删除或合并，清理历史需要单独授权。
- feedback、stage artifact 和 trace 仍随运行增长；减少的是完整业务线表重复存储，不是零存储增长。
- 已导出的 XLSX 是独立文件快照；未来当前结果导出必须绑定 generation+revision，完整导出并发一致性仍待实现。
- 真实 Stage 2/3 视觉回归本轮未运行；识别 Prompt/模型调用未改。归因队列故障恢复、前端真实 API 接入等已有待办没有因本次调整而自动完成。
