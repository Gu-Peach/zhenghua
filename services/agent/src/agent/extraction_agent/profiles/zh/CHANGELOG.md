# ZH Profile变更记录

## 2.3.0 — 2026-10-19

- 正式ZH入口接入用户已验证的zh_crop2.2.1局部高清补全能力。
- 三阶段Prompt、分类案例、1初扫/7补全案例统一在prompts/zh维护；Profile引用源资源，打包时生成包内resources。
- 原Prompt/Expected/图片/任务输入/裁剪参数保持；仍使用zh_native，不改变Python算法、标准结果字段或坐标含义。
- 版本和来源摘要更新，包含README/CHANGELOG作为可查看、可上传资源。
- 用户移除zh_crop/history后，新调用统一为zh；已冻结任务保留自身资源。不恢复已删除目录，不自动上传、重绑或重提取。

2.1.1及更早记录保留在原prompts/zh/CHANGELOG.md和已冻结规则包中。
