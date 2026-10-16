# 三表前后端数据管理交付

用户明确范围：先适配前后端数据管理，上传→Agent提取→新表落库后续再改。未改用户正在调整的Agent Graph/Prompt/样例，不调用真实模型。

## 实现

- 新应用服务simple_management.py、simple_index.py和profile_references.py读写三表；项目树从drawing_index.pages生成稳定工作区/图纸ID，业务页与PDF物理页分离。没有索引时显示真实空态，不伪造分类。
- API v2使用Simple* DTO、batch_id/record_version，取消结果版本/线号单元依赖。查询支持分页/过滤/搜索，跨页目标仅按确认的PDF物理页定位，私有资源路径必须属于当前项目。
- PDF经PyMuPDF校验，保存私有project-assets并登记项目/校验和。用户显式选择规则，上传幂等且不覆盖已有不同内容；失败可重试，source_saved区分是否真正保存。
- 本地规则目录只读登记key/version/checksum/resource_ref，内容变化后重新登记；预览通过授权API返回虚拟资源路径及图片。删引用受所有者/FK保护，不删除规则文件。
- 新migration 20261016000000部署manage_extraction_connection服务专用RPC：锁项目/行、检查所有者/归档/版本、增改删幂等、before/after和回执保存到项目management元数据。不增加业务表，字段仅改单行。
- 项目删除先归档、检查活跃任务，删除项目命名空间内登记的Storage文件，再删除DB行。失败保留归档项目供刷新重试，未知其他项目路径拒绝签名/删除。
- Server默认不初始化旧Agent代理/旧纠错/旧规则候选服务；Supervisor明确返回未接入。Web上传不发送提取消息，AI按钮/输入禁用并说明当前边界。
- OpenAPI与generated.ts同步；保留原Auth实现和三项Auth回归。旧业务合约用例移动至legacy fixture，当前默认回归针对新三表。

## 验证

- Server默认14项通过（11项新数据管理、3项原Auth）。新增失败回归先复现旧projects查询400，再改接新表通过。
- Web typecheck/lint/production build通过；10项Playwright HTTP夹具通过，覆盖空/加载/失败/无权限、桌面/390px窄屏、长文本、仅保存上传、跨页双图、行内编辑及冲突保留草稿/重试幂等。截图位于.runtime/simple-management-browser，已视觉核对登录及工作台桌面/窄屏。
- 新Server源文件mypy及Ruff通过。API生成命令路径修正到apps/api/src。
- 本地真实Auth/Storage/HTTP验收通过：一次性账号→规则登记/资源预览→PDF保存/签名读取/重复请求→合成图纸索引/私有PNG→行增改删/重放/版本冲突→项目与文件清理。新三表最终各0行，Auth用户回到3、Storage对象回到358；未清理既有用户或文件。
- RPC在事务回滚探针通过后部署、登记迁移；验证页项/所有者/冲突/审计/重放，合成数据回滚。一次初始低权限嵌套DO探针触发本地Postgres signal 11，数据库自动恢复、事务回滚；改用has_function_privilege权限元数据检查后通过，未再次执行故障探针。

## 使用与限制

用户8000服务未擅自停止；需要在该终端Ctrl+C后按原uvicorn命令重启，再刷新5174。当前数据管理无需启动Agent；独立Stage2内存测试照常使用，未被改为落库。

Agent正式导入/分类/提取/持久化、旧纠错/候选发布、跨进程任务恢复不在本轮接入。上传暂不生成页面图片或分类，只保存原PDF；图纸预览和新增连接依赖已存在的JSON索引。管理审计/回执保存在项目JSON，后续规模增大需评估体积；未来Agent需遵守ADR-0020的批次及图纸索引契约。

验证入口：services/server/tests、services/server/scripts/verify_simple_management.py --allow-local-write、apps/web的playwright test。默认测试不写真实库或调用模型；真实本地验收需显式开关，自动清理合成数据。未将运行截图、日志或临时文件加入Git。
