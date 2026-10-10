# 2026-10-08 静态工作台

## 范围

- 新建 React + Vite + TypeScript 应用 `apps/web`；
- 保留旧 `frontend/` 和 `backend/`；
- 添加 pnpm workspace 根入口；
- 建立标准 `src` 分层和应用 README；
- 添加真实振华图纸作为静态证据预览资产。

## 页面

- Mock 登录页；
- 项目、工作区、图纸三级目录；
- 11 字段结构化线表；
- 图纸来源与示例证据标记；
- 三阶段处理过程；
- 静态 AI 会话栏；
- 用户菜单、项目切换与退出入口。

## 验证

```text
corepack pnpm typecheck:web  PASS
corepack pnpm lint:web       PASS
corepack pnpm build:web      PASS
```

浏览器已验证：

- 登录跳转；
- ZH/ABB 项目切换；
- 工作区与图纸选择；
- 线表、图纸证据、处理过程 Tab；
- 用户菜单；
- 浏览器控制台无错误。

响应式 CSS 已覆盖 `1320px`、`1080px` 和 `760px` 三个断点。本次浏览器运行环境未成功应用窄屏 viewport override，正式移动端截图基线仍保留为后续项。

## 未包含

- Supabase Auth；
- 新 FastAPI 接口；
- 数据库读取；
- SSE；
- 真实 AI 对话；
- XLSX 下载。
