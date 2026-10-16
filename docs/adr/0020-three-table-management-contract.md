# ADR-0020：三表数据管理契约与提取入口边界

状态：Accepted。用户2026-10-16要求前后端适配新三表，并明确选择“先适配前后端数据管理，提取链路后续再改”。

## 决策

- FastAPI入口继续是apps/api/src/main.py、端口8000；应用服务位于services/server，新业务管理路径仅读写extraction_profiles/projects/connection_rows。Agent任务表保留，仅项目删除前检查活跃任务，不调用旧业务RPC或Supervisor。
- API版本2.0.0，以batch_id、record_version替代result_version_id/result_revision和wiring_unit_id。项目直接关联规则引用；工作区/图纸ID由project_id及JSON索引稳定派生，不新建表、不伪造业务页标。字段转换集中在Server索引适配及Web apis层。
- PDF上传由Server校验并保存到私有project-assets，按actor+Idempotency-Key分配稳定项目ID，保留校验和，重复请求验证已有文件不覆盖。上传仅登记文件，页面渲染/分类/连接提取待Agent接入。UI必须明确选择规则，自动任务与AI输入保持禁用。
- 登记规则仅保存本地受限Profile的key/version/checksum/resource_ref。资源预览校验当前checksum及路径边界，通过授权API返回Prompt/JSON和图片；客户端不能指定任意文件路径。规则内容变更后需重新登记新checksum，已有项目不自动重绑。
- 行级CRUD使用服务端专用manage_extraction_connection RPC：锁项目和连接、检查所有者/归档/record_version，保存before/after及幂等回执到项目drawing_index.management。共享端子排单元已取消，所有字段仅改本行；页项唯一键不以原理号代替。
- 项目删除先核对updated_at/活跃任务，再归档、清理索引登记的项目命名空间文件，最后删除项目及级联结果。失败保留归档项目可重试。规则被项目引用时不能删除，删引用不会删除本地规则文件。

## 兼容与限制

旧表已由用户授权删除，不建立旧表兼容视图；旧数据和旧修订/候选工作流不恢复。历史Web/Server旧合约用例保留为legacy fixture，默认回归切换至新三表，原Auth回归仍执行。独立Stage2内存测试和用户正在修改的Agent Prompt/Graph不变。

本轮不会改变schema中的三张业务表数量；新增migration只增加RPC。未来Agent写入必须遵循本契约：来源/目标PDF物理页、业务页与workspace_code分离，发布图纸索引和当前批次后再供UI读取。管理审计与幂等回执目前位于项目JSON，人工编辑规模增长时需评估体积及保留策略。

## 验证

14项后端默认/Fake用例，10项浏览器夹具，Web类型/lint/生产构建通过；真实本地Auth/规则引用/PDF与图片Storage/JSON索引/行CRUD/重放/冲突/删除验收通过，合成账号及文件清理。数据库RPC合成探针回滚后部署并登记，未调用VLM或启动Agent。一次低权限嵌套DO探针触发本地Postgres进程signal 11，数据库自动恢复且事务回滚；权限改为ACL元数据验证后通过，未重复触发该探针。
