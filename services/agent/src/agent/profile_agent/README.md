# Profile Agent

独立规则助手：填充图纸模板、维护图片/Expected、诊断规则问题，并通过受控工具修改草稿。本轮交付Python接口、CLI和可注册APIRouter；尚未接入规则页、共享宿主或正式发布。没有新增端口，不依赖Supervisor/旧自完善或评测表。

## 行为

- 新模板使用统一的实际端子/证据约束及提取阶段Pydantic Schema，填写公司特征、放线标记、功能区拆分、页号/命名映射和跨页模式。通用模板位于本模块，不会作为可选规则混入生产Profile目录。
- 新标准不自动借用ZH原图和答案。用户上传实际图片后，模型通过附件ID生成案例及manifest引用，生成的Expected保持待用户确认。
- 现有规则按本地Profile key/版本建立隔离副本，自动增加patch版本；当前生产文件保持原样。长驻Agent新建副本时重新读取源规则并核对复制前后摘要。
- 每轮先加载有限的规则、代表案例答案及图片，优先用户原图；截断/未读文件和图片覆盖范围显式返回。模型可通过工具继续读取。每轮最多6张图、12次工具调用，使用现有图像像素预算。
- 诊断区分规则问题、案例问题、模型偏离、混合与证据不足。明确归因需要实际原文锚点；没有实际输出对照不能记录为模型偏离，未读取的Python后处理不能被排除。
- `intent=discuss`仅提出精确before/after建议；确认接口绑定具体proposal ID及版本，应用同一份修改。`intent=edit`表示本轮用户明确要求编辑，可直接调用编辑工具，无需再确认同一授权。一轮最多一次原子写入，可包含多个文件。
- Schema、Profile身份、共用模板约束和Python代码受保护。修改过的Expected需要重新确认；已有精确Prompt/规则编辑不会被后续“重新填表”静默覆盖。
- 所有写操作只作用于用户隔离草稿。输出的ZIP为`published=false`，不注册数据库规则、不上传Bucket、不更新生产引用或历史项目。

## 模块

| 文件 | 职责 |
| --- | --- |
| models.py | 模板字段、草稿/建议/诊断/编辑、确认与回复DTO |
| template.py | 通用约束、模板渲染、固定阶段Schema及案例安装 |
| store.py | SQLite修订头、不可变文件快照、权限/摘要/版本、幂等与before/after审计 |
| validation.py | 引用/图像/Expected、完整性、正负例、确认状态和适配器边界校验 |
| evidence.py | 首轮规则/代表案例/原图装载及覆盖范围 |
| tools.py | 当前用户/草稿绑定的读取、看图、诊断、建议和编辑工具 |
| graph.py | LangGraph模型—工具循环，流式公开回复和工具事件 |
| service.py / factory.py | 独立调用、对话缓存、确认和包输出 |
| api.py | 未来鉴权宿主可注册的`/v1/profile`路由，不自动挂载 |
| __main__.py | 本地独立开发入口 |

## 本地使用

在仓库根目录安装依赖后进入Agent目录。默认状态保存在被Git忽略的`.runtime/profile-agent`；无需启动HTTP服务或Supabase。

```powershell
Set-Location E:\project\zhenghua_test
.\.venv\Scripts\python.exe -m pip install -e services/agent
Set-Location services/agent
$profileActor = "11111111-1111-4111-8111-111111111111"

# 新建可填写的空模板；输出draft_id/revision，后续使用该ID
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor create --key demo --name "新图纸规则"

# 或建立现有ZH规则的编辑副本
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor create --key zh --name "振华修订" --source-profile zh
```

后续命令中的`<draft-id>`使用创建结果。`revision`必须使用最新值，上传图片、确认案例和修改规则均会产生新修订。

```powershell
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor show <draft-id>
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor attach <draft-id> --revision 1 --image E:\sample\source.png
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor attach <draft-id> --revision 2 --image E:\sample\target.png

# 以下会调用配置的真实模型，需要显式开关；配置沿用services/agent/.env
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor ask <draft-id> --revision 3 --message "根据原图及我的描述填充模板：放线标记是小圆圈，功能区和页码读取标题栏……" --edit --allow-real-model

# 诊断不加--edit；可用--observations指定实际输出/期望对照的JSON数组文件
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor ask <draft-id> --revision 3 --message "为何端子总被添加GTR前缀？先定位规则和案例证据，给出建议" --allow-real-model

# 确认或拒绝回复中的具体proposal；这里不再次调用模型
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor confirm <draft-id> --revision 3 --proposal <proposal-id> --accept
```

查看Expected后，将其相对路径及`read`返回的checksum写入JSON映射，例如`{"resources/wiring_examples/scan/case.expected.json":"sha256:..."}`。确认只针对当前文件摘要，模型没有此工具。

```powershell
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor read <draft-id> --file resources/wiring_examples/scan/case.expected.json
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor confirm-expected <draft-id> --revision 4 --checksums E:\sample\confirmed.json
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor validate <draft-id>
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor export <draft-id> --revision 5
..\..\.venv\Scripts\python.exe -m src.agent.profile_agent --actor $profileActor audit <draft-id>
```

只读/创建/确认/校验/导出命令不调用模型。`ask`使用的模型需支持标准`tools/tool_calls`；默认测试使用Fake网关，尚未验证真实端点的生成质量。CLI身份用于本地开发，不能用作生产鉴权。

## Python与宿主接入

```python
from src.agent.profile_agent import (
    DraftCreate,
    ProfileActor,
    ProfileTurn,
    create_profile_agent,
)

agent = create_profile_agent()
actor = ProfileActor(user_id=verified_user_uuid)  # 从宿主的鉴权上下文传入
draft = await agent.create(DraftCreate(key="zh", display_name="振华修订", source_profile="zh"), actor)
reply = await agent.ask(
    draft.draft_id,
    ProfileTurn(message="分析为何会添加额外前缀", expected_revision=draft.revision),
    actor,
)
# 用户确认具体建议后：
updated = await agent.confirm(draft.draft_id, reply.proposals[0].id, draft.revision, True, actor)
```

未来共享宿主可`include_router(create_profile_router(agent, authenticated_actor_dependency))`，与其他Agent共用8100。Actor由宿主验证，模型工具参数不包含身份或根目录。当前没有修改共享宿主，也没有让浏览器直接调用未鉴权Agent。

路由提供草稿创建/读取、文件读取、图片上传、`turns`/`turns/stream`、建议读取/确认、Expected确认、校验、审计和导出。它们尚未进入当前业务Server OpenAPI/TS客户端；正式接入时再生成对应契约。

## 校验与限制

- 导出前要求三个阶段的实际图片案例、至少一个初扫正例和负例、所有引用可解析、Expected符合当前Schema且经用户确认。旧分类答案`page_number`在副本中规范化为`drawing_page_number`，不改原文件或事实。
- `stage3_cases`/Schema中的stage3沿用现有资源包兼容名称，表示Stage2内部定向补全案例。
- `reference_mode/page_number_mode=adapter_change_required`会阻止就绪包输出。模板只能使用现有adapter；Prompt无法替代新的确定性解析代码。命名字段描述向function/正整数页号的映射，实际文件名仍沿用当前提取器，不支持任意文件命名算法的自动改造。
- 就绪仅表示结构、引用和确认有效，不证明实际识别准确率。当前不运行自动提取评测或生产发布。
- 持久化为本地开发用SQLite和不可变修订，重开Agent可恢复草稿/建议/历史。生产存储、正式版本发布和跨主机部署由后续Server接入负责。
- 取消可能发生在已授权的原子写入之后，已提交修订保留；重试前读取最新revision/audit。导出包保留在草稿的exports目录，不能把输出路径当作已发布引用。

设计与交付见[ADR 0026](../../../../../docs/adr/0026-independent-profile-agent.md)及[实施记录](../../../../../docs/service/agent/changelog/2026-10-17-profile-agent.md)。
