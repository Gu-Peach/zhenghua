# ADR-0001：独立 Agent 服务与受控结果提交

> 状态：Proposed  
> 日期：2026-10-08

## 背景

现有 FastAPI 同时承担业务 API、文件存储和长时间 VLM 提取。任务可能运行数分钟到数小时，模型失败、checkpoint、局部重跑和离线评测的生命周期与普通业务请求不同。未来还需要支持 ZH、ABB 等不同 Profile，以及用户反馈后的局部重提取和规则改进。

## 决策

1. Agent 作为独立 Python 服务部署，默认暴露内部端口 `8100`。
2. 业务 Server 默认端口 `8000`，持有用户权限、项目、生产结果和结果版本。
3. Agent API 创建异步 run，Worker 执行 LangGraph；不在业务请求进程中运行小时级任务。
4. Agent 只能返回 `ResultProposal/ResultPatch`，不能直接覆盖生产线表。
5. Server 使用权限、Schema、业务规则和 expected version 校验 proposal，通过后创建新结果版本。
6. 在线提取与反馈修复使用 LangGraph；工具、checkpoint、trace、eval、Profile 沙箱和发布门禁组成项目自己的 Agent Harness。
7. V1 不叠加 AutoGen、CrewAI 等第二套上层编排，避免双重状态、checkpoint 和工具权限模型。

## 备选方案

### 与 Server 同进程

优点是部署简单；缺点是长任务影响 API 生命周期，无法独立扩容、限流、探活和验证，因此拒绝。

### Agent 直接访问并写业务数据库

优点是调用链短；缺点是绕过权限、乐观锁、版本和审计，模型错误可能直接污染生产数据，因此拒绝。

### 引入完整第三方多 Agent 平台

优点是可能提供现成 UI、trace 或 supervisor；缺点是与现有 LangGraph 重叠、增加模型供应商和状态耦合。V1 使用可替换 adapter 保留未来选择，不立即引入。

## 结果

正面影响：

- Agent 可以独立部署、测试、扩缩容和熔断；
- 旧业务结果在 Agent 失败时仍然可用；
- 所有变更可通过 proposal、diff 和结果版本审计；
- Profile 改进可以在沙箱和离线评测中完成。

代价：

- 需要 Server-Agent 内部契约、服务认证和事件同步；
- 需要 Agent runtime/checkpoint 数据存储；
- 本地开发至少运行两个端口；
- 需要额外契约测试和部署监控。

## 验证条件

- Agent `8100` 可以独立探活；
- Server 不依赖 Agent 进程读取已有项目结果；
- Agent 无生产线表写权限；
- 提交并发冲突时 Server 拒绝旧 `base_result_version`；
- Agent 停机或重启后 run 可从 checkpoint 恢复；
- Profile 候选未经 Eval 和人工审批无法变为 ACTIVE。
