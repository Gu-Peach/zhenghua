# 第一个混合纠错终端验收脚本

日期：2026-10-11。用户要求改用终端查看所有阶段输出，并明确本轮只写“规则无问题／拒绝候选”第一个脚本，第二个等待用户构造规则问题。

## 实现

- `services/agent/agent_test/2.纠错agent/run_acceptance.py` 只使用 stdlib/httpx：自然语言输入、对话 SSE、run SSE/恢复游标、产物/proposal/模型输出/业务结果查询，不导入 Agent/tool、不访问数据库、不读服务端 `.env`，不选择内部 Stage 路径。
- 混合 direct/同页/跨页输入由 Supervisor 拆批；脚本展示阶段输出、路由理由和 before/after，等待用户明确确认，再监看原位更新与异步归因。
- 判定规则无问题且无候选则结束，无待拒绝事项；意外建议候选时只允许人工拒绝，拒绝成功仍记录预期偏差为 FAIL。证据不足记录 INCOMPLETE，不伪造规则正确结论。
- 核对当前 connection/unit ID、线号、代次、revision、目标字段与未关联字段；可加载人工 expected JSON。不提供人工 baseline 时不声称视觉准确率通过。要求三类路由、Stage 2/3 和四类模型输出实际覆盖。
- `--run-id` 只监看，不重新提交或恢复任务；POST 不盲目重试，断线时 GET SSE 按已知 seq 续读。JSONL/summary 按事件写入，任务退出不会自动取消。
- 新增 owner-scoped run 模型输出接口，以及按记录的 user/conversation 过滤的 Supervisor 模型输出接口。只展示结构化模型任务输出、公开理由/诊断，排除隐藏推理、Prompt、请求头和图片数据；旧 Trace 无原始内容则如实标记不可用。
- 修正批次提示文字：只描述实际涉及的路径，不再让直接答案看起来也要执行 Stage 2/3。

## 验证与边界

离线 Mock HTTP 覆盖规则无问题、规则建议后拒绝、证据不足、未确认退出；服务端回归覆盖模型输出过滤、用户隔离、多反馈归因 Trace。相关 Supervisor/确认链回归、strict mypy/Ruff 和 CLI help 通过。

没有实际运行真实模型验收、修改 test0、迁移数据库或重启服务。API/Worker 需由用户重载最新代码，之后按目录 README 启动脚本。输出文件仍在已有忽略的 `agent_test/**/runs/` 下，包含用户项目数据，不提交版本库。第二个脚本/真实规则缺陷样例均未创建。
