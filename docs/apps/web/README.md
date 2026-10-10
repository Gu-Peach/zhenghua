# apps/web 前端归档

> 当前状态：交互式 Mock 工作台完成；真实鉴权、业务 API 与持久化事件流未接入  
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

- `/login`：Mock 登录、密码可见性、加载和错误状态；
- `/projects/:projectId`：项目工作台；
- 左侧：项目、工作区、图纸树；
- 顶部：线表工作区、图纸库、规则库导航；操作区上传 PDF 或导出结果；
- 中间：线表结果和图纸证据；跨页终点支持悬浮高亮及目标页定位；
- 右侧：Supervisor 主 Agent 运行监工；显式开启模拟链路后，Mock 支持 PDF 三阶段、自然语言线表修复、问题归因和候选规则展示。未触发时为空态，不展示历史或预置运行过程；
- Header：处理状态、通知、用户菜单与退出入口。

## 当前接口

`src/apis` 已定义以下前端接口边界：

- 登录、退出；
- 项目列表、项目详情；
- 项目线表连接；
- 最新运行事件。
- 图纸库和规则库；
- Supervisor 提取/修复事件流。

默认 `VITE_USE_MOCKS=true`，但运行模拟仍需用户显式打开工作台内的“模拟链路”开关。上传后先展示项目源 PDF，Stage 1 完成后才显示工作区和拆分页；Stage 2/3 依序展示处理中和完成状态。Mock 只模拟前端事件与结果 patch，不会执行 PDF 识别、数据库写入或生产规则发布。`VITE_USE_MOCKS=false` 的 run/SSE 和库查询适配器已预留，后端端点、DTO、权限及恢复契约仍待联调确认。

## 后续

1. 接入 Supabase Auth 和路由守卫。
2. 接入 `apps/api` 项目树和连接分页接口。
3. 将线表搜索、筛选和分页迁移为服务端查询。
4. 接入持久化 run 与 Supervisor 事件 SSE，统一后端 DTO 和鉴权。
5. 增加正式的登录页和项目工作台端到端截图基线。
