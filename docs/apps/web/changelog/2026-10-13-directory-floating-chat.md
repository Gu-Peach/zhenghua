# 图纸库原地展开与悬浮聊天

日期：2026-10-13。

## 行为与文件

- `components/DrawingDirectory.tsx`：当前项目→工作区→PNG 图片的原生可折叠目录；图片展开后调用既有 projectApi 读取，复用 DrawingPreview 原地展示。包含空态、加载、无权限/失败重试，目录展开不切换路由或线表过滤条件。
- `components/FloatingAgentPanel.tsx`：右下角固定按钮及非模态悬浮对话窗口，默认收起，上传时打开；支持窗口关闭按钮和 Escape，关闭后焦点回按钮；隐藏后组件仍挂载，消息草稿/历史保留，任务订阅继续，新消息/任务状态显示角标。
- `components/AiPanel.tsx`：增加关闭操作与可见性参数，重新打开后按现有跟随尾部状态恢复进度显示。
- `views/ProjectView.tsx`：接入目录与悬浮聊天，去掉固定右栏及其缩放条；左侧导航、线表/跨页预览与 Agent 会话控制仍由当前项目页维护。
- `assets/styles.css`：工作台两列布局、层级目录、悬浮窗口/按钮及窄屏适配。

此实现替代 2026-10-12 的图纸平铺/点击切换线表表现。API/数据库契约未变化。

## 验证

- `corepack pnpm typecheck:web`、`lint:web`、`build:web` 通过。
- `apps/web` 内 `.\node_modules\.bin\playwright.cmd test tests/workbench.spec.ts`：13 项通过，全部使用 HTTP fixtures。
- 回归覆盖目录多级展开、跨工作区图片懒加载、线表过滤保持、权限失败重试；聊天开关/Escape/焦点返回/草稿保留/隐藏期间进度续传且不重复入队，原上传检测确认和纠错确认仍通过。
- 检查 `.runtime/web-tests/` 下的目录、悬浮窗口、登录、工作台桌面/窄屏截图；390px 窄屏窗口边界、发送按钮可见且页面无横向溢出。

本轮没有真实模型调用、数据库改动或服务重启；真实 Agent 由用户继续手动验收。Web 开发模式刷新即可加载新展示。
