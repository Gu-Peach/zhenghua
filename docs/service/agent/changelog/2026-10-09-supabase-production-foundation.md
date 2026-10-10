# Agent Supabase 生产基础

日期：2026-10-09  
状态：本地真实 Supabase 已验收；托管远端待部署

## 已实现

- Agent 在 `AGENT_PERSISTENCE_BACKEND=supabase` 时使用持久 Run、Event、Artifact、Proposal、Checkpoint repository。
- 任务队列使用数据库租约原子领取，可由独立 Worker 跨进程消费。
- 原始 PDF 写入私有 `project-assets` 的 `projects/{project_id}/original.pdf`，数据库保存 checksum、MIME 和大小。
- Stage 1 分类完成后创建工作区与图纸记录，并把页面图写入 `projects/{project_id}/workspaces/{workspace_id}/drawings/{drawing_id}.png`。
- 阶段 JSON、checkpoint 与最终 XLSX 写入 `projects/{project_id}/runs/{run_id}/{stage}/...`。
- `/health/ready` 在 Supabase 模式下执行真实连接检查。

## migration

本地 Supabase 已应用 `20260918000000`、`20261005000000`、`20261009000000`、`20261009010000`、`20261009020000`、`20261009030000` 和 `20261009040000`。最后一份 migration 修正项目级联清理顺序，不改写已应用历史。

## 验证

`services/agent/scripts/verify_supabase_production_foundation.py` 已通过，覆盖：

- PDF 上传、下载与 checksum；
- 工作区、图纸及页面图片发布；
- 私有 Bucket、签名 URL、owner/anon RLS；
- 带租约队列、并发事件序号、Artifact 与 Proposal；
- Checkpoint 乐观锁；
- 同一结果版本并发分配 `1000..1007` 线号；
- 测试项目和对象的最终清理。

Agent 测试共 82 项通过；本次涉及文件 Ruff 与 `compileall` 通过。全包 strict mypy 仍受迁入 `zh_workflow` 的既有类型债务阻塞，未把该债务误记为本次已完成。

## 剩余边界

- 托管远端 Supabase 尚未部署和复验。
- 业务 Server 的项目创建/上传 API、面向 Web 的分页查询和事件代理尚未实现；底层结果查询与事务化版本提交已由后续 Agent 数据库工作流完成。
- Correction evidence、accepted feedback、Profile candidate/eval/release repository 已由后续 migration 和 Supabase adapter 持久化。
- 完整进程中断续跑和 ZH 真实 VLM 字段级基线仍待执行。
