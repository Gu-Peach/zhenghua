# 三阶段提取子 Agent 基座

日期：2026-10-08

## 实现范围

- Stage 1 `PageClassifierAgent`：读取单张已渲染页面的 Plant Function 与图纸业务页号，同时保留 PDF 物理页号。
- Stage 2 `PageScannerAgent`：每次只扫描当前来源页；页面扫描请求不包含目标图片字段。
- Stage 3 `CrossPageResolverAgent`：按一个跨页 task 接收来源页和索引目标页，输出仅包含终点补全的结果契约。
- 三个阶段各自提供可独立调用的 LangGraph 子图和强类型 Pydantic 请求/响应。
- `ProfileBoundStageDispatcher` 根据已锁定 `ProfileBinding.adapter` 分发实现。
- `LegacyZhStageAdapter` 复用现有 ZH `VLMClient` 的三个阶段方法，动态使用 Profile 内 Prompt 与图片 Few-shot，并复用既有 parser、Schema 重试和 HTTP 重试。
- ABB `native_pending` 没有注册为 ZH adapter，不能回退误用振华提取规则。

## 保持在 Agent 之外的步骤

PDF 渲染、Drawing Index、跨页任务构建、跨页目标检索、归一化、去重、确定性字段校验、proposal 组装与业务数据保存不属于这三个 VLM 子 Agent。它们将在 M8 Extraction Workflow 中编排；Agent 只返回阶段候选结果。

## 验证

- Agent 单测与契约测试：48 passed，默认不访问真实 VLM。
- ZH Prompt/Few-shot 适配测试确认三阶段都从当前 Profile 路径加载原图样本。
- 严格类型检查、Ruff 和旧后端回归通过。

## 未完成

- 尚未实现串联三子图的完整 Extraction Workflow、PDF 渲染入口、跨页索引器、checkpoint/event 持久化或 proposal API。
- 尚未执行付费 VLM 真实图片字段级回归；ZH 结果验收和 M4 首页识别的生产启用门槛仍待完成。
- ABB Profile 仍是 experimental，尚无可执行 native stage adapter。
