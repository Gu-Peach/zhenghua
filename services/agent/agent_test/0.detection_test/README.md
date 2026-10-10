# 阶段 0：终端 HTTP 验收

脚本 `run_acceptance.py` 只上传 PDF、发送用户输入、显示 Agent 返回的 SSE 消息和保存对话记录。不导入 Agent 实现，不调用检测/VLM/PDF 渲染/Supabase 工具。Supervisor 在服务端自主决定是否调用 ProfileDetection。

## 启动

从仓库根目录启动本轮代码的 Agent API；模型配置由服务读取 `services/agent/.env`。阶段 0 不需要开启 inline Worker。

```powershell
.\.venv\Scripts\python.exe -m uvicorn agent_service.main:app --app-dir services/agent/src --host 127.0.0.1 --port 8100
```

另开终端运行；省略 PDF 路径时会列出本目录案例供选择：

```powershell
$env:AGENT_ACCEPTANCE_ALLOW_REAL_MODEL="true"
.\.venv\Scripts\python.exe "services\agent\agent_test\0.detection_test\run_acceptance.py"
```

也可指定案例：

```powershell
.\.venv\Scripts\python.exe "services\agent\agent_test\0.detection_test\run_acceptance.py" "services\agent\agent_test\0.detection_test\EZ原理图与放线表对照(1).pdf"
```

如果 API 设置了 `AGENT_INTERNAL_TOKEN`，客户端终端需设置同名环境变量；脚本不会读模型或 Supabase 密钥，也不会输出 Bearer token。`--base-url` 可指向不同端口的 Agent。旧服务需加载本轮代码后才具备新接口，不由脚本自动重启服务。

## 人工输入与验收

上传后默认发送“只识别类型，先让我确认，暂不提取”。应看到简短 Supervisor 计划、ProfileDetection 调度消息，以及包含具体类型/置信度的确认问题。即便高置信，也必须等待用户回答。

终端输入任意自然语言，例如：

- `确认`：认可已检测类型。
- `不对，是 ABB 图纸`：人工改选。
- `暂不确认`：应继续询问，不能直接接受。
- `刚才确认的是什么类型？`：检查短期记忆。
- `/quit`：结束客户端会话。

第一次用户输入携带上传附件 ID；后续输入刻意不带附件、run_id 或 profile_hint。Agent 必须从服务端记忆中找回确认对象。Unknown 情况下只说“确认”不能选类型，应明确回答 zh/abb。确认后结束类型识别，不执行 Stage 1/2/3，不产生业务线表结果版本。ABB 人工确认只是类型选择，不启用 experimental 提取能力。

真实验收需显式设置 `AGENT_ACCEPTANCE_ALLOW_REAL_MODEL=true`；未设置时脚本不会请求服务。报告保存到本目录 `runs/<时间-会话>/transcript.json`、`memory.json` 和 `summary.json`，默认不提交。摘要输出模型、案例和每轮接口耗时；API 未提供费用时记录 unknown，不伪记为 0。脚本返回 0 仅表示 HTTP 交互完成，不等于识别准确率通过；请结合 PDF 首页人工核对，案例预期标签不得从文件名猜测。

## 记忆边界

本轮新增的是单进程短期记忆，最多 256 个会话、每会话最近 12 轮；按 conversation_id/user_id 隔离。服务重启、多实例切换或会话淘汰后不恢复。原来只有任务 checkpoint，没有 Supervisor 对话历史；长期记忆仍未实现。

同一服务进程内可继续已有会话，使用之前打印的 ID 和相同 user-id：

```powershell
.\.venv\Scripts\python.exe "services\agent\agent_test\0.detection_test\run_acceptance.py" --conversation-id "此前打印的会话ID"
```

会话 PDF 保存于服务端私有 `.runtime/conversations`，当前附件入口只供类型识别，不创建业务项目。停止客户端不会删除输入案例或历史产物；runtime 附件的清理需按测试数据保留策略执行。

## 默认回归

```powershell
.\.venv\Scripts\python.exe -m pytest services/agent/tests/integration/test_detection_conversation_api.py -q
```

以上使用 Fake Gateway，不调用真实模型。手工运行验收脚本则请求真实 Agent 服务，模型调用由服务端配置决定。
