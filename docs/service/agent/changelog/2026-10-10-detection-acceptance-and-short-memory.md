# 阶段 0 HTTP 验收与短期记忆

日期：2026-10-10。决策：[ADR-0006](../../../adr/0006-supervisor-short-term-memory-and-detection-acceptance.md)。

新增 `agent_test/0.detection_test/run_acceptance.py`，只调用附件、Supervisor 流式回合和会话快照接口，终端模拟用户输入。后续回合不补附件/run/profile hint，检测和确认由 Agent 根据自己的上下文执行。报告写入 ignored runs 目录，不含鉴权 header。

此前 Supervisor HTTP 回合未加载历史，本轮新增有界进程内记忆：按会话绑定操作者，记住最近 12 轮、当前附件、待确认检测及最终 ProfileAssignment。turn_id 重试返回缓存结果，输入不同不能复用 ID；会话和附件隔离测试覆盖越权读取。

新增 DETECT_PROFILE/QUERY_CONTEXT 意图。检测只使用 PDF 物理首页，并在此入口把高置信结果也转为等待确认。用户只说“确认”可认可原候选；Unknown 必须明确选择。确认仅完成类型选择，不排队完整提取或写入业务结果版本；实验性 ABB 可被确认为类型，但不会自动启用提取。

新增附件和 SSE 回合接口，统一普通回合与流式回合的记忆注入。短计划、调度和最终消息来自服务端；生产完整提取、Correction/Improvement handler 保持已有入口。已确认同一类型沿用检测时的 Profile 版本。

默认 Fake API 回归覆盖识别→确认→记忆追问、Unknown 改选、重试幂等、操作者/附件隔离、类型附件不得启动提取以及脚本导入边界。未调用真实 VLM，未重启已有测试进程。真实案例准确率仍需通过终端脚本人工验收。

记忆仅适用于同一服务进程，最多 256 会话，不持久化到 Supabase，不支持重启/跨实例恢复；长期记忆未实现。上传附件属于 private runtime，保留与清理另按测试数据策略处理。

验证结果：103 项 Agent 测试通过；148 个源文件的 strict mypy、Ruff、compileall 和 diff --check 通过。验收脚本默认禁止真实模型，必须显式设置 `AGENT_ACCEPTANCE_ALLOW_REAL_MODEL=true`；本轮未运行真实 VLM，因此没有虚构准确率、费用或耗时结论。

阶段 0 首次真实请求发现兼容性问题：Supervisor 内部把结构化上下文作为 Python 对象放在 `message.content`，部分 OpenAI-compatible 端点只接受字符串或多模态数组。模型网关现统一在 HTTP 边界将 mapping 序列化为 JSON 字符串，并以 MockTransport 回归验证；多模态数组保持原样。修复后的真实模型验收需重新加载 Agent 服务后执行。

重新加载后发现同一端点还拒绝了自动生成的 `response_format`（服务端要求以 `--structured-output` 启动）。网关现将 provider structured-output 设为显式 opt-in：`output_model` 仍执行本地 JSON/Pydantic 校验，但默认不发送 `response_format`；只有 `ModelRequest.json_mode=true` 才发送。
