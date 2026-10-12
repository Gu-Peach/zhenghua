# apps/web 前端归档

> 当前状态：真实 Supabase Auth、Server 工作台 API、持久 Agent 事件流和资源库已接入。
> 应用说明：[apps/web/README.md](../../../apps/web/README.md)

## 所有权

`apps/web` 是新 React + Vite + TypeScript 前端。旧 `frontend/` 在迁移期保留，不作为新代码的依赖。

源码边界：

- `apis`：请求 Client、接口函数、DTO、Mock 适配；
- `assets`：全局样式与打包资源；
- `components`：可复用业务组件；
- `directives`：预留底层 DOM 行为适配；
- `hooks`：可复用交互状态；
- `layout`：应用布局；
- `router`：React Router 路由和后续守卫；
- `stores`：跨页面状态；
- `views`：路由页面。

## 当前页面

- `/login`：Supabase Auth 登录、续期和错误状态；
- `/projects/:projectId`：项目工作台；
- 左侧：项目、工作区、图纸树；
- 顶部：线表工作区、图纸库、规则库导航；操作区上传 PDF 或导出结果；
- 中间：Server 分页线表和图纸证据；跨页终点支持悬浮高亮及目标页定位；
- 图纸库：只展示当前项目的图纸目录，不展示项目文件夹或工作区分组；左侧项目树仍保留工作区层级，用于业务导航和上下文定位；
- 规则库：从 `/api/v1/rule-library` 查询所有登录用户共享的可用资源包；每个规则标识展示最新版本，不显示草稿状态；
- 右侧：Supervisor 主 Agent 运行监工，展示真实任务阶段、确认与结果事件；
- Header：处理状态、通知、用户菜单与退出入口。

## 数据与可见性

- 图纸目录来自项目详情 API 中的 drawings；图纸条目保留所属 workspace ID 供选择后定位，但目录视觉上不渲染工作区分组。
- 规则库由 Server 使用当前登录用户 JWT 查询 `profile_resource_packages`，不是扫描前端或本地 `prompts/` 文件夹。
- Supabase RLS 允许所有 authenticated 用户读取 `candidate_id is null` 的手工规则包；Improvement 隔离候选仍只对创建者/审核者可见。删除仍仅创建者可执行。
- ABB 最新规则为 `abb@1.1.2`，状态 active；旧 1.1.0/1.1.1 checksum 保留。前端展示最新版本，Agent 新任务也选择最新 active 版本。

## 检查

质量检查和浏览器夹具命令见 [应用 README](../../../apps/web/README.md)。Playwright 的图纸目录与共享规则状态测试使用 HTTP fixtures，不调用真实模型或修改数据库。

2026-10-12 最终检查：Web typecheck、lint、production build 和 11 项 `workbench.spec.ts` 回归通过；检查登录、工作台和图纸库桌面/窄屏截图。图纸库覆盖空目录与跨工作区点击定位；共享规则 RLS 已用非创建者 authenticated 身份在真实本地 Supabase 验证。详见 [资源目录收尾记录](./changelog/2026-10-12-resource-library.md)。
