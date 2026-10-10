# Agent M4 Profile Router

日期：2026-10-08

## 实现

- Profile Detection Graph 只渲染 PDF 物理首页，不读取后续页面。
- ZH/ABB 使用独立 `rules.json`，Router 在一次 VLM 请求中动态注入候选识别规则。
- active 且高置信 Profile 返回 `PROFILE_SELECTED`；未知、低置信和 experimental 返回 `WAITING_INPUT`。
- 用户确认由 `ProfileAssignmentService` 执行，生成包含版本、checksum、规则和资源映射的不可变 ProfileBinding。
- `ProfileBoundExtractionDispatcher` 根据 Binding 的 adapter key 分派兼容提取实现，不判断供应商品牌。
- 新增公开规则接口：`GET /v1/profiles/{key}/versions/{version}/rules`。
- 新增显式真实 VLM 测试脚本，默认测试不产生模型费用。

## 验证

- Agent 默认测试：27 passed。
- 旧后端回归：53 passed，2 skipped。
- mypy strict：49 source files，无错误。
- Ruff check/format：通过。
- 三份真实 PDF 均成功渲染且证据页固定为 `pdf_page_number=1`。
- 真实 ZH PDF + Fake VLM：`PROFILE_SELECTED -> zh`。
- 真实 ABB PDF + Fake VLM：检测为 `abb`，因 experimental 返回 `WAITING_INPUT`。

## 待完成

- 尚未调用真实 VLM；M4 关闭前需显式运行 ZH、ABB、UNKNOWN 案例并记录准确率、耗时和费用。
- Server run API 和前端确认交互仍属于后续集成任务。
