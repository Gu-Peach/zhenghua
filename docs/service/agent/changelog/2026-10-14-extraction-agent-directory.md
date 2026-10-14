# 独立提取Agent目录迁移

用户先将agent_service包内容移到src根，并把Prompt/Profile移入src/agent/extraction_agent。本轮在这个工作区上迁移61份提取实现：阶段Agent、文档应用/Graph、模板VLM及兼容适配器、专属模型、PDF/图片/JSON/Excel/checkpoint工具、模板策略、局部提取和proposal构建。

保留共享API、Supervisor/纠错/改进编排、通用Domain、Harness、Profile注册/包管理、Worker与数据库/Storage层。没有复制实现、调整函数体、Graph拓扑、字段约束、Prompt或expected。仅变更导入、测试patch目标、路径、包配置、资源元数据引用/校验和。

共享正式包随用户目录改为src，提取实现为src.agent.extraction_agent。API入口改src.main:app --app-dir services/agent；脚本搜索根改services/agent，测试conftest/README引用同步。现有run_stage2_groups.py文件及参数保留。pyproject包发现/数据资源和.gitignore图片例外更新，避免迁移资产遗漏。

src/config.py的__file__父级按用户扁平化后位置更新；默认Profile资源根改src/agent/extraction_agent/profiles。现有.env只改AGENT_PROFILE_ROOT的旧目录引用，模型/数据库等其他配置不变；.env.example同步。没有启动或重启服务。

静态对照结果：61份迁移文件；254份Python源/脚本/测试可解析，排除导入及已列明的路径引用后AST与迁移前相同；新src内部导入没有缺失源码目标。116份原有资源字节相同，3份代码路径/校验和元数据调整。模型类名和Schema字段保持原实现；没有执行Schema运行时生成或业务回归。

未运行pytest、业务/真实模型测试、提取、API或数据库/Storage写入；未发布规则、提交Git或覆盖旧运行结果。静态比对不能替代真实调用验收。设计见[ADR-0017](../../../adr/0017-extraction-agent-directory.md)，当前模块见[Extraction Agent README](../../../../services/agent/src/agent/extraction_agent/README.md)。
