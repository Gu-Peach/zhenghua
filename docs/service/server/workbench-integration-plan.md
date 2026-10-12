# 真实工作台接入执行计划

日期：2026-10-12。范围：不修改数据库 Schema，不修改 Agent 核心工作流。

1. 基础已实现：apps/api FastAPI 入口、services/server 领域服务；复用已有表、RLS、私有 Storage、Agent HTTP。JWT 由 Supabase Auth 验证；所有对象强制项目权限，浏览器不得持有内部 Token/service-role。
2. 基础已实现：Web 默认真实数据，Supabase 登录；项目/工作区/图纸树、服务端分页线表、页码/线号只在组首显示、编辑表格、原页/目标页下方预览、真实规则包三阶段 Prompt 与样例。
3. 基础已实现：通过 Server 安全转发 Agent 8100 的真实 HTTP/SSE，不绕过 Profile/结果/规则人工确认；上传自动发起检测，确认后运行三阶段。公开计划/依据与阶段卡片保留；支持续传、刷新和错误处理。
4. **进行中（剩余浏览器纠错验收）**：24 项默认 API、5 项 HTTP 夹具 Playwright、lint/build/strict mypy 通过；真实 CRUD/双图/回滚及 Bucket 三阶段资源面板/图纸索引通过。用户授权真实模型后，浏览器上传/检测/人工确认已产生三阶段成功结果（5 页/13 连接，约 226 秒）。浏览器进程退出，后续结果刷新/纠错/确认/归因尚未验证；续跑因自动审批服务 403 配置故障未执行，保留一次性项目，不重提取。见 changelog/2026-10-12-live-agent-acceptance.md。共享队列 Fake claim 失败是此前验收记录，不阻止现有 Worker 已完成的真实提取。

## 数据契约

数据库是事实来源。线号来自 wiring_units.wire_number，原理号来自 wiring_connections.principle_number，不混用。业务页码与 PDF 物理页号分开。跨页目标依据 connection_evidence/raw_payload 的明确引用，不按端子文本猜目标。未解析引用展示不可定位原因。

手工修改使用既有 apply_confirmed_result_patch、完整 before/after、record_version/revision 校验与审计；不得绕过并发校验。项目删除先清理 Storage 对象再事务删除 DB，失败保留项目并允许重试；不可在存在活跃 run 时删除。规则从 agent-profile-assets 内容地址包读取，签名图片 URL。

## 验收边界

端子新增/删除使用 Server PostgreSQL 既有表事务（ADR-0011）；新增归入已有线号，明确来源和跨页目标，删除存证据审计并保留空单元与其他 ID。无 DSN 明确失败，不用分散 REST 写入模拟事务。

Mock 仅显式演示，真实接口失败不可回退伪造数据。Agent 连接由 Server 加内部凭据代理，不将 8100 内部 Token 下发浏览器。与用户所说“直连 Agent 端口”的能力一致，但保持网络/鉴权边界。新增公开契约同时生成 OpenAPI 类型。
