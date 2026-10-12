# ProfilePatchBuilder 输出契约修复

## 证据

用户提交的验收输出显示 Supervisor AUTHORIZE_PROFILE_CANDIDATE 成功，下游恢复失败。只读 Supabase Trace 进一步确认 agent=profile_patch_builder、schema=ProfilePatchModelOutput、validation_errors=invalid_json（不是已证明的具体字段缺失，也不是 Supervisor 不支持授权意图）。失败 JSON 原文没有放进公开文档。

## 改动

- agents/profile_patch_builder.py：与本地校验同源的动态 JSON Schema 注入 system Prompt，记录 Profile/反馈 metadata，不启用 provider response_format。
- prompts/profile_patch_builder.md：纯 JSON 对象、顶层字段/枚举、operation 字段，content 为完整文件字符串而非片段/diff，换行/双引号/反斜杠转义和包相对路径；保留沙箱与人工/评测发布门禁。
- tests/unit/test_profile_patch_schema.py：先复现缺少 Schema/序列化约束，再验证完整 Schema、Mock HTTP 请求、中文/换行保真和非法输出严格拒绝。

## 验证和边界

11 项相关离线测试通过（Patch 契约、Diagnosis 契约、Supervisor 协作），不调用模型。未修改数据库、test0、Bucket、生产 Profile，也未停止/重启服务。

服务与独立 Worker 需加载新代码后，仅恢复失败 Improvement run；已接受的数据修订不重新提交。本修复只证明请求契约完善，不声称真实补丁生成/候选回归/规则发布已经通过。Stage 2/3 不变。
