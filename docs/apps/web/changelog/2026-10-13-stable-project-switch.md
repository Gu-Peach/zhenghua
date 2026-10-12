# 项目切换局部加载与稳定目录

日期：2026-10-13。

原闪屏来自 keyed ProjectWorkspace 重新初始化后返回整页加载页；目录随 projectId 重拉且 API 按 updated_at 倒序，更新时间变化会使项目前移。

ProjectView 目录 effect 不再依赖 projectId，上传/重命名/删除等显式管理动作仍刷新。目标项目已在列表时，用摘要初始化工作台框架，详情/结果只在中间加载；新项目状态保持独立，不显示旧线表。详情成功后在原位置更新父级摘要。规则库读取独立于项目详情，规则读取失败有独立重试，不阻塞整个项目。

Server 项目列表改为 created_at.asc/id.asc，顺序与选择和更新时间无关；契约结构和数据库不变。排序端需用户重载 Server，Web 开发版刷新即可；没有停止运行服务或模型任务。

17 项 HTTP fixture 浏览器回归通过，延迟详情期间检查 Header/目录可见、中央加载、旧表不可见；更新第二项目时间并来回切换，目录顺序与请求数量均不变。29 项 Server 默认测试、相关 Python Ruff、Web typecheck/lint/build 通过。加载中桌面/390px 窄屏截图在 `.runtime/web-tests/project-switch-loading-*.png`，已检查。
