# 2026-10-16：独立Explain Agent

## 交付

实现位于services/agent/src/agent/explain_agent，使用既有目录而非创建拼写重复目录。LangGraph四节点为load_authorized_context→collect_evidence→answer_question→present_explanation；复用共享ModelGateway，不依赖旧Supervisor或修改现有提取。

只读三表，先校验项目所有者再读取项目内的行，验证可选批次与行版本。图纸来自项目JSON索引，物理页与业务页独立；图片仅允许配置私有桶和当前项目路径，返回短期签名地址。缺图、坐标无效、规则版本缺失时保留事实与明确缺口。

优先解释evidence.profile、record.source_note、references、review_reasons等已保存依据。当前值与提取快照不同时显示差异，不能用旧说明证明新值；未保存的模型调用过程或历史思考不补造。模型本次只读取文字事实，不做看图复核，签名地址/Storage路径不注入提示。

有界进程内多轮会话固定用户/项目/行，数据/Prompt指纹变更时清除旧历史。相同turn缓存仍重查权限和上下文；无权、版本冲突时不调用模型。同会话忙请求拒绝，取消/失败不保存无效回答。

提供Python工厂、显式真实模型开关CLI以及可挂载HTTP/SSE router。宿主必须注入鉴权身份，正文不能自带actor。模块未挂载共享服务、未接前端，不新增端口。新Prompt加入setuptools资源清单；独立router的OpenAPI通过TestClient验证，业务Server OpenAPI不变。

## 验证

- 本模块20项离线测试：原页/跨页/同页、规则冻结与回退、路径与坐标、缺证据、字段差异、权限/版本/会话范围、重试缓存、多轮刷新、容量/取消/失败、身份注入与SSE、CLI门禁及配置注入。
- 与共享ModelGateway/Harness、Server默认测试共59项通过；Ruff通过，9份新源码strict mypy通过；CLI帮助可加载。
- 全部使用FakeModelGateway、MockTransport和TestClient；未调用真实模型或数据库、部署migration、改.env、发布规则、启动/重启服务或执行旧Agent清理。真实数据和前端联调待后续接入。

设计见[ADR-0023](../../../adr/0023-independent-explain-agent.md)，调用及接口字段见[模块README](../../../../services/agent/src/agent/explain_agent/README.md)。
