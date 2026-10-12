# 项目目录固定排序

日期：2026-10-13。

WorkbenchService.projects 查询改为 `created_at.asc,id.asc`，替代更新时间倒序。项目更新后保持创建顺序，同时间由 ID 确定；选择状态不参与排序。RLS/权限和响应 Schema 保持不变。

29 项默认 Server API 测试、相关 Ruff 和 Web 目录顺序回归通过；没有数据库写入或 migration。当前服务由用户重载后使用新查询。
