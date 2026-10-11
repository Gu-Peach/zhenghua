# 纠错批次与 Profile 资源包：代码实现与待部署事项

日期：2026-10-11。用户确认[改造方案](../correction-agent-refactor-plan.md)后实施；按要求优先功能开发，没有运行长时真实模型验收。

## 已实现的代码

- Supervisor 输出结构化 `correction_items`，从自然语言 hints 补齐检索条件，服务端强制注入操作者。目标歧义才追问；业务字段白名单和项目 owner/editor 检查保持受控。
- 一个批次冻结同一项目/结果/Profile，确定性排序为 direct patch、Stage 2、Stage 2→Stage 3。多字段修改合并成一个 proposal，确认时只提交一个新结果版本，避免多批次相互版本冲突。
- Correction item、Stage 2/3 响应和跨页任务清单进入 `agent_artifacts`，完成事件晚于持久化。再次执行可复用已保存 item/阶段响应。Stage 2 新引用按数据库页面目录重新定位，缺失或不唯一则 `needs_review`；Stage 3 保持来源起点锁定。
- Proposal 携带实际 artifact 与 run Trace 引用；受控提交为每条反馈登记 accepted payload，异步 Improvement 对多个反馈逐项诊断。
- Improvement 读取纠错及原始 run 的 artifact/trace、当次 Profile 内容、expected JSON 和原图/目标图图片。Trace 新增原始模型响应；旧 Trace 若缺响应不能追溯补造。为控制视觉预算，一次附加最多两张 Few-shot 图片，覆盖范围显式记录，缺证据应输出 SOURCE_INSUFFICIENT。
- 创建候选前需用户明确授权，拒绝结束本次改进任务而不改生产规则。候选沙箱复制完整资源包，不再仅复制 Profile 目录；候选标识、adapter 等受确定性保护，包有独立版本、checksum 和 manifest 文件校验。
- 私有 `agent-profile-assets` 适配器支持不可覆盖上传、完整性校验、缓存恢复、冻结版本加载、文本/图片签名 URL 展示，以及发布/回滚入口。实际路径为 `key/version/package_digest/resources/...`，避免同版本候选互相覆盖。
- 包内附带 `schema.json`，收录三个阶段的 Pydantic Schema。Few-shot manifest 必须引用实际图片和 expected JSON。Python 策略仍在代码中，候选只能给出代码修改建议。
- Supervisor 下一轮从数据库读取当前 proposal/diagnosis 作为待确认上下文，结果确认与规则候选确认分开。

## 主要文件

- `domain/models/{supervisor,result_data,correction,runs,proposals,improvement}.py`：扩展公共模型，旧单项输入继续兼容。
- `application/{supervisor_handlers,correction_workflow,improvement_run_executor,improvement_workflow,supervisor_conversation}.py`：串联混合任务、确认与归因。
- `tools/{extraction_runner,result_data,event_presenter}.py`：持久阶段调用、范围控制与事件展示。
- `profiles/package.py`、`infrastructure/supabase_profile_packages.py`：自包含资源包和 Supabase 适配器。
- `supabase/migrations/20261011010000_profile_resource_packages.sql`：资源包表、RLS、不可变内容约束、私有 Bucket、发布/回滚 RPC。
- `scripts/publish_profile_package.py`：显式 bootstrap 部署工具，不是纠错验收脚本。

## 部署顺序（尚未执行）

当前 Agent 配置的 Supabase host 为 `127.0.0.1`；Docker daemon 不可连接。因此没有应用 migration、上传资源包或修改运行服务的环境变量，也没有启动/停止/重启任何已有服务。

1. 启动现有本地 Supabase，并通过正常 migration 流程应用 `20261011010000`（不要重置数据库）。
2. 显式发布当前已人工确认的 ZH bootstrap 资源包：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/publish_profile_package.py zh `
  --user-id "<已有 Auth 用户 UUID>" --approve-bootstrap
```

3. Agent API 和 Worker 的环境均设置 `AGENT_PROFILE_PACKAGES_ENABLED=true` 后加载新代码。默认 `false` 保持本地兼容模式；启用却无 active 包时启动失败，不静默换用本地文件。
4. 使用内部鉴权请求 `GET /v1/profiles/zh/versions/1.0.0/package?checksum=<原 Profile checksum>`，获取文本、包清单和短期图片签名 URL。未来浏览器仍需由业务 Server 代理，不暴露 service-role。
5. 复用 test0 手工注错，在现有 Supervisor 接口输入纠错、确认 diff、查看诊断和确认/拒绝候选。

## 验证与限制

- 26 项相关默认离线测试通过（包括新增合并多个字段、item 复用、自包含包/篡改校验）；Ruff 和全包 strict mypy 通过。
- bootstrap 脚本帮助入口已运行；没有真实 VLM、真实数据库迁移/RLS验证、真实包上传或 Web 验收。
- 非提取 run 仍使用现有 protocol 1 Worker；持久 item 可供重新执行复用，但本次没有实现其过期 RUNNING 自动接管/fencing，也不能宣称纠错跨进程故障恢复已完成。阶段持久化 Gate A 的 protocol 2 接管仍只覆盖正式 FULL_EXTRACTION。
- 对话记忆仍为进程内短期记忆；业务 run/artifact/proposal 持久化与对话恢复是不同能力。
- 自动执行完整真实 Profile 回归并未新增；仍走现有 EvalRunner/评测报告/人工门禁接口。创建 candidate 不代表评测通过或可发布。
- 资源包对象与 PostgreSQL 没有统一事务；中断上传可能留下未引用对象，不在异常路径删除历史对象。发布/候选状态跨事务的失败仍需重试及运维核对。
- 人工注错标记 `origin=manual_injected_test_error` 从记录传播到归因。它可验证链路，不作为确定幻觉或规则问题的证据。

