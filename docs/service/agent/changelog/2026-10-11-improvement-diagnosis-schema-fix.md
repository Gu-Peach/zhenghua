# Improvement 归因输出契约修复

## 失败点

用户混合验收的归因 run `6f387fe8-2a1c-416e-8c11-e6d5d1ce6cba`
返回自定义 `diagnosis/summary/root_cause` 等字段，缺少 Diagnosis 的必填字段，
因此本地 Pydantic 校验报 MODEL_SCHEMA_INVALID。
归因 Prompt 只要求“符合 Diagnosis schema”，却未向模型发送实际 Schema；
Gateway 的 `output_model` 只负责本地校验，不会自动把 Schema 注入模型请求。

此前修订已成功提交。用户验收记录显示三个目标 end_terminal 为 `2/1/X3:1`，
结果代次和连接/单元/线号稳定，revision 为 3，人工预期和授权字段检查均通过。
归因失败不回滚数据，不需要重新注错或重复提交 proposal。

## 修复

- `agents/improvement_diagnoser.py` 在 system 消息中动态追加
  `Diagnosis.model_json_schema()`，包含所有必填字段、类型、嵌套对象、枚举及禁止额外字段约束。
- `prompts/improvement_diagnosis.md` 明确字段名称，不允许自定义 envelope、字段替换或
  `MANUAL_TEST_INJECTION/CORRECTION_PIPELINE_VERIFIED` 等非契约枚举。
  人工注错来源写入 explanation；类别按证据选择，不强行判定规则无问题。
- 严格 Pydantic 校验不放宽，不自动修补旧输出，不增加 Schema 错误重试。
  保持 provider `response_format` 默认关闭，与现有端点兼容。
- 不改公共模型/API、数据库 Schema、Stage 2/3、图纸 Profile 资源包或生产规则。

## 验证与边界

- 补测试先复现请求缺少 Schema；修复后 24 项相关离线测试通过。
- 新增回归覆盖运行时 Schema/$defs 与 Diagnosis 一致、Fake 与 Mock HTTP 请求、
  SOURCE_INSUFFICIENT 与规则缺陷输出保持原意、旧自定义输出继续严格拒绝。
- 修改文件 Ruff 与 Agent 全包 strict mypy（158 文件）通过。
- 未调用真实模型、未修改数据库/Storage、未重启服务、未恢复真实任务。
  后续真实归因仍待用户执行，不能把结构校验修复等同于规则正确性验收。

## 只重试归因

重启 API/Worker 加载修复后，通过现有内部接口
`POST /v1/runs/6f387fe8-2a1c-416e-8c11-e6d5d1ce6cba/resume`
恢复这个 FAILED 的归因 run（无请求体）。如果配置内部 Token，必须携带同一
`Authorization: Bearer ...`；不是 Supabase service-role key。

该操作会重新调用真实归因模型，应由用户显式发起。
随后使用纠错终端脚本 `--run-id 6f387fe8-2a1c-416e-8c11-e6d5d1ce6cba`
监看输出即可。不恢复前一个纠错 run，不重复提交，不重新注错。
只监看模式记录 MONITOR_ONLY，不会自动把之前的 ERROR 验收摘要改成完整 PASS。
