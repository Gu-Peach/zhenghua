# 独立 Profile Agent

用户确认本轮先做独立Agent核心，规则页与正式发布后接。实现位于`services/agent/src/agent/profile_agent`，不改正在并行开发的Explain、共享宿主、业务API或原始Profile。仅在Agent包配置中增加本模块Prompt资源。

## 实现

强类型模板分离公共端子/证据/输出约束与图纸特有的放线标记、分区、页码映射和跨页模式。新建草稿不复制ZH品牌和图像答案。既有规则通过只读本地Registry建立自包含副本并增加patch版本；源文件复制前后核对摘要。

LangGraph使用统一模型网关，首轮自动加载有限规则、代表案例/Expected和原图，显式报告截断和覆盖范围；模型按需调用读取、看图、诊断、建议、模板填充和精确编辑工具。流式事件仅公开回答和工具结果，不包含内部推理；记录模型、调用耗时、尝试次数、usage及输入图片数。

建议保留精确before/after及可验证原文；确认绑定proposal/revision/checksum，同事务登记状态、修订和审计。用户明确修改指令使用intent=edit，直接编辑草稿，不重复请求授权。Expected确认是独立动作，模型不能通过参数冒充确认。拒绝、过期、越权、路径/Schema错误不产生草稿修改。已有精确编辑不被后续填表静默覆盖。

SQLite保存用户隔离的修订头、建议、对话和before/after审计，文件使用不可变修订目录。包输出复用现有构建/校验器，ZIP时间戳固定、可重复核对，published恒为false。旧分类Expected字段别名仅在副本规范化，提取Schema与生产资源不变。

## 范围

提供Python SDK、独立CLI与可注册APIRouter，不自动注册8100，不增加端口/数据库业务表，不触发模型评测或正式发布。CLI真实模型操作必须显式`--allow-real-model`；本轮测试为Fake VLM及已有真实图像案例，未运行真实模型、用户PDF或写入Supabase。

未来规则页需绑定具体建议的确认动作及Expected确认，不应让模型把任意肯定句当作全局发布许可。正式发布由Server校验数据库引用/基线版本后提交，既有项目不自动重绑。本地开发SQLite不是已交付的生产草稿服务。

验证：33项Profile Agent用例与3项Registry回归全部通过；13个源码文件的strict mypy（follow-imports=silent）及模块/新测试Ruff通过。CLI帮助可加载，缺少--allow-real-model时ask在调用前被拒绝。覆盖真实图片到VLM输入、初始规则/代表案例装载、新模板、GTR诊断、确认/拒绝/并发/过期、原子批次、路径/Schema/权限、Expected重确认、导出包校验、重开恢复、源规则刷新、工具预算及总结失败后的已提交结果。未跑真实模型质量/费用评测、前端E2E或Supabase集成（本轮均未接入）。

命令与调用示例见[模块README](../../../../services/agent/src/agent/profile_agent/README.md)。
