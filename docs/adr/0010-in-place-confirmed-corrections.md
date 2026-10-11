# ADR-0010：确认后的局部修订原位更新

- 状态：Accepted for implementation
- 日期：2026-10-11
- 用户明确要求：直接答案、Stage 2/3 重识别均覆盖当前记录，保留前端索引，避免整份结果重复存储。

本决策覆盖 ADR-0004 中“每次局部纠错复制新结果版本”的规则。完整 PDF 提取仍创建结果集合；局部纠错在用户确认 proposal 后，通过受控事务更新当前集合中的既有连接，connection/unit/evidence ID 和线号保持不变。Stage Agent 不直接写库，确认门禁不取消。

`result_versions.version` 改为提取集合的代次；新增 `revision` 表示集合内修订次数。proposal 冻结 base revision 和各 connection record_version。事务锁项目/结果/目标连接，验证 owner/editor 权限、当前代次、Profile、before 值及预期版本。每次成功修订增加 revision/目标 record_version，并保存 feedback before/after、操作者、时间和 proposal receipt。重复确认先读 receipt，不再更新或生成重复审计。

旧历史版本不清理、不覆盖。只允许更新最新非 superseded 集合，防止用户误选旧连接。前端用稳定 connection ID 更新对应行，revision 用于缓存/并发校验；导出须标注 generation+revision，不能再把 result_version_id 单独当作永不变化的导出快照。

实施顺序：1) 契约/新 migration；2) 内存/Supabase 受控提交适配器；3) 确认消息/结果读取与必要回归；4) 本地迁移部署。真实模型手工验收由用户执行。不删除历史数据、不重启服务。
