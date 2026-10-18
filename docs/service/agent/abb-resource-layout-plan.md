# ABB资源布局统一

2026-10-18，用户要求旧名称全量对齐ZH。只调整本地资源组织和引用，不改变ABB识别规则、Expected字段值、Graph或十四列输出，不发布、不操作数据库/模型或当前运行目录。

1. 已完成：核对生效/历史资源及全部使用位置，记录24份资源的当前内容摘要。
2. 已完成：`page_cross_page_completion.md`改为`page_connection_completion.md`，`examples_wiring/annotated`改为`examples_wiring/lv11`，`stage3`改为`completion`，`provenance.json`改为`quality-provenance.json`，新增样例README；历史原图/离线案例移至`tests/fixtures/abb_reference`，不再混入生效资源包。
3. 已完成：同步Profile1.2.2及引用、图片准备脚本和测试资源引用，3Python AST/Ruff、16项manifest引用/44项摘要、Schema/加载绑定通过，17份Prompt/图片/Expected迁移前后字节相同。未运行测试、模型或数据库操作。

ZH也保留manifest协议键`stage3_cases`，本轮保持公共加载协议不改，只把该键引用的物理目录统一为`completion`。ABB现有目标局部图功能保留，不为凑目录添加重复Prompt；ZH/XMZ资源不变。历史设计/发布记录保留其当时路径，在新交付说明中提供映射。
