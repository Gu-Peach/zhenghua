> > "services/agent/agent_test/0.detection_test/EZ原理图与放线表对照(1).pdf"  
> > 项目：d99bc079-2860-5e52-b439-0d7f15f1ce29；PDF：5 页；Agent：http://127.0.0.1:8100
> > 用户：请识别这份 PDF 的图纸类型让我确认，确认后执行三阶段提取并落库。
> > [Agent/SUPERVISOR_PLAN] 用户明确要求识别类型并执行三阶段提取落库，属于完整处理流程。
> > [Agent/WORKFLOW_DISPATCHED] 已开始识别图纸类型，后续阶段会持续反馈。
> > [Supervisor] 首页识别为振华电气图纸（zh），置信度 98%。请确认，或说明正确类型。
> > 用户（确认 / 指定类型 / /quit）：OK
> > 用户：OK
> > [Agent/SUPERVISOR_PLAN] 用户回复 OK 确认了待确认的图纸类型检测候选，且上下文显示已请求完整提取。
> > [Agent/WORKFLOW_DISPATCHED] 已收到确认，正在恢复对应任务。
> > [Supervisor] 已收到确认，正在恢复对应任务。 类型已确认，三阶段提取任务已登记；进度以持久事件为准。
> > 持久任务：847f640b-57c4-4d43-aff6-dc3c73de882d；断线/服务重启后可用 --run-id 847f640b-57c4-4d43-aff6-dc3c73de882d 继续监看。
> > [Supervisor/RUN/RUN_CREATED] run created
> > [Supervisor/RUN/RUN_STARTED] RUN_STARTED
> > [Supervisor/RENDER/STAGE_STARTED] STAGE_STARTED
> > [Supervisor/RENDER/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/RENDER/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/RENDER/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/RENDER/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/RENDER/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/RENDER/STAGE_COMPLETED] STAGE_COMPLETED
> > [Supervisor/PAGE_CLASSIFICATION/STAGE_STARTED] STAGE_STARTED
> > [Supervisor/PAGE_CLASSIFICATION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_CLASSIFICATION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_CLASSIFICATION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_CLASSIFICATION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_CLASSIFICATION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_CLASSIFICATION/STAGE_COMPLETED] STAGE_COMPLETED
> > [Supervisor/PAGE_SCAN/STAGE_STARTED] STAGE_STARTED
> > [Supervisor/PAGE_SCAN/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_SCAN/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_SCAN/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_SCAN/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_SCAN/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/PAGE_SCAN/STAGE_COMPLETED] STAGE_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/STAGE_STARTED] STAGE_STARTED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/BUILD_CROSS_PAGE_TASKS/STAGE_COMPLETED] STAGE_COMPLETED
> > [Supervisor/CROSS_PAGE_COMPLETION/STAGE_STARTED] STAGE_STARTED
> > [Supervisor/CROSS_PAGE_COMPLETION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/CROSS_PAGE_COMPLETION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/CROSS_PAGE_COMPLETION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/CROSS_PAGE_COMPLETION/STAGE_COMPLETED] STAGE_COMPLETED
> > [Supervisor/VALIDATION/STAGE_STARTED] STAGE_STARTED
> > [Supervisor/VALIDATION/ITEM_COMPLETED] ITEM_COMPLETED
> > [Supervisor/VALIDATION/STAGE_COMPLETED] STAGE_COMPLETED
> > [Supervisor/RUN/RUN_COMPLETED] RUN_COMPLETED
> > [Supervisor] 任务处理完成：SUCCEEDED；数据库结果 12 条。
> > 接口执行完成不等于准确率验收通过；请检查字段差异/人工复核报告。
> > 验收记录：E:\project\zhenghua_test\services\agent\agent_test\1.3stage\runs\20261011-151314-d680ba1b

已核对 `result.md` 和实际 Supabase：这次运行确实完成，状态为 `SUCCEEDED`，最终结果版本为 **1，存有 12 条连接明细**。

存储位置如下：

| 阶段             | 内容                                 | 存储位置                                                                                                           |
| ---------------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Stage 1 页面分类 | 拆页图片                             | 私有 Bucket `project-assets`                                                                                       |
| Stage 1 页面分类 | 工作区、业务页号、物理页号、图片引用 | `workspaces`、`drawings`                                                                                           |
| Stage 1/2/3      | 逐项结构化结果与完整阶段快照         | `agent_artifacts.payload`，类型为 JSONB                                                                            |
| 最终结果         | 校验后的线表版本、连接和证据         | `result_versions`、`wiring_units`、`wiring_connections`、`connection_evidence`；通过 `wiring_connection_rows` 检索 |

所以，**第一阶段不只是存 Bucket**：图片存 Bucket，分类结果同样存数据库。第二、第三阶段的中间结果在 `agent_artifacts` 中，下一阶段从已提交快照读取。

在 `agent_artifacts` 中筛选：

```text
agent_run_id = 847f640b-57c4-4d43-aff6-dc3c73de882d
stage = PAGE_CLASSIFICATION / PAGE_SCAN / CROSS_PAGE_COMPLETION
```

其中 `gate_a_item` 是逐项结果，`gate_a_manifest` 是全阶段快照，`gate_a_model` 是模型结果缓存。

这次 Stage 2 实际扫描了 3 页、跳过 2 页，Stage 3 完成了 3 个跨页任务。分类清单仍有 2 页标记 `needs_review`，最终版本是 `draft`，因此链路成功不代表字段准确率已经验收通过。
