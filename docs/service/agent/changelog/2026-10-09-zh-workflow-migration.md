# ZH 工作流迁入 Agent 服务

## 范围

- 将 ZH 的 PDF 渲染、页面索引、跨页任务构建、checkpoint、归一化校验和 XLS/XLSX 生成代码迁入 `agent_service.zh_workflow`。
- 三阶段 VLM 调用改由 `PageClassifierAgent`、`PageScannerAgent`、`CrossPageResolverAgent` 的 LangGraph 子图，经 Agent 自己的 OpenAI-compatible Model Gateway 调用。
- Prompt 和图片 Few-shot 随 ZH Profile 放在 `services/agent/prompts/zh`；测试 runner 不导入旧 `backend`，也不写数据库。
- 配置兼容原有 `VLM_*` 模型和提取参数；增加 Windows checkpoint 临时替换重试。

## 运行与产物

从仓库根目录运行 `services/agent/scripts/run_three_stage_extraction.py`。输入 PDF 后，在指定输出目录产生 Stage 1、Stage 2、Stage 3 JSON、最终 `table.json` 和标准 `table.xlsx`；配置导入模板后额外生成模板格式工作簿。

Agent HTTP 服务尚未开放完整 PDF 长任务接口；本次交付是可直接测试的本地全链路 CLI。当前 CLI 只支持 ZH Profile，ABB 仍是后续接入项。

## 验证

- Fake Stage 离线 PDF 工作流生成三个阶段 JSON、分类图片目录和 11 列 XLSX。
- 原生阶段 adapter 测试确认模型消息包含图像 Few-shot。
- 旧 `VLM_*` 配置映射测试通过。
- Windows checkpoint 临时 `os.replace` 权限错误重试测试通过。
- 未执行真实 VLM 请求；全量 pytest 因当前环境未安装 pytest 未运行。
