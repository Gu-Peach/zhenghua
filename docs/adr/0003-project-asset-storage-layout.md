# ADR-0003：项目资产私有 Bucket 与对象路径

状态：Accepted  
日期：2026-10-09

## 背景

旧 `images` Bucket 为公开 Bucket，对象按一次旧任务放在 `{job_id}/agent`、`groups`、`pages` 和 `source` 下。该结构把运行产物、业务工作区、页面图片和原始文件混在一起，无法直接映射“项目 -> 工作区 -> 图纸”前端树，也允许匿名枚举全部对象。

## 决策

1. 保留旧 `images` Bucket 和旧对象，迁移验收前不删除、不移动。
2. 新建私有 `project-assets` Bucket，生产新链路只写该 Bucket。
3. 原始 PDF 直接位于项目目录：`projects/{project_id}/original.pdf`。
4. 页面图片按项目和工作区嵌套：`projects/{project_id}/workspaces/{workspace_id}/drawings/{drawing_id}.png`。
5. 阶段产物按运行隔离：`projects/{project_id}/runs/{run_id}/{stage}/{artifact_name}`；导出文件位于同一运行的 `exports` 子目录。
6. 对象路径仅使用不可变 UUID。项目名称、工作区名称、业务页码和原始文件名保存在数据库中，避免改名或同名导致对象冲突。
7. 浏览器不持有 service-role key。项目成员只能通过数据库权限检查和短期签名 URL 读取对象；浏览器默认不能直接写入或枚举整个 Bucket。
8. `document_files.storage_bucket/storage_path` 与 `drawings.image_bucket/image_path` 是对象定位事实来源，前端不拼接旧任务目录。

## 结果

- Storage 虚拟目录与前端项目树一致，同时保留稳定、不因改名变化的对象键。
- 原始 PDF、页面图片和运行产物具有清晰生命周期与删除边界。
- 旧公开 Bucket 可在完成回填、引用核对和前端切换后单独下线。

## 未选择的方案

- 使用项目名或工作区名作为路径：名称可修改、可重复且包含不安全字符。
- 继续把 `agent/groups/pages/source` 放在任务目录下：任务是执行记录，不是业务目录。
- 将新 Bucket 设为公开：无法满足项目成员隔离和签名 URL 要求。
