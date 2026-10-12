# 图纸目录与共享规则库

日期：2026-10-12。

## 已实现

- 图纸库移除旧项目文件夹组件，平铺当前项目全部工作区内图纸，不展示工作区标题；左侧项目树不变。
- 图纸条目保留工作区和图纸 ID，点击仍能定位对应线表；目录为空时提示等待页面分类。
- 规则库不再展示草稿/候选/已发布三态；用户手工上传或创建的规则包存储后即为“可用”，每个 key 展示最新版本。
- 所有登录用户共享手工规则包；删除按钮仍只对创建者出现。Improvement 隔离候选不进入规则库。

修改位置：`apps/web/src/views/ProjectView.tsx`、`components/LibraryPanel.tsx`、`apis/projects.ts`、`apis/types.ts`、`assets/styles.css` 和 `tests/workbench.spec.ts`。

## ABB 实际状态

通过当前 Server 配置连接的 Supabase 查询包元数据：

- `abb@1.1.0`、`abb@1.1.1` 由 migration 从旧 draft 升为 active，原对象与 checksum 保留。
- `abb@1.1.2` 已作为 18 文件不可变包上传并逐文件读回校验；规则库和 Agent 默认选择 1.1.2。
- 非创建者 authenticated 数据库会话可以读取五个手工规则版本，并看不到一个 Improvement 隔离候选。

迁移 `20261012000000` 取消手工包草稿门槛并允许同 key 多个 active 历史版本；`20261012010000` 将共享读取限定为 `candidate_id is null`，候选仍保留创建者/审核者范围。Server 只返回每个 key 最新 active 包。

## 验证

- `corepack pnpm typecheck:web`、`lint:web`、`build:web` 均通过。
- 在 `apps/web` 执行 `.\node_modules\.bin\playwright.cmd test tests/workbench.spec.ts`：11 项通过，使用 HTTP fixtures。
- 检查 `.runtime/web-tests/` 的登录、工作台、图纸库桌面/窄屏截图；图纸目录无项目/工作区分组，窄屏无页面横向溢出。
- 没有真实模型调用、项目业务数据修改或用户服务重启；仅应用上述 additive migration 并新增 ABB 1.1.2 规则资源包。
