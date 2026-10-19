# ADR-0037：运行界面只使用数据库规则包

2026-10-19，用户明确要求将zh、abb、xmz三套规则上传，并让上传PDF的选项和Extraction Skills只从数据库获取。

## 决策

- 原始开发资源仍位于本地profiles/prompts，本地提取CLI保持；界面不再将本地catalog合并为可选规则。
- 数据库extraction_profiles保存身份/版本/checksum和私有project-assets中的完整ZIP引用。可选目录仅包含有效 `storage://project-assets/profiles/...zip` 记录，每key选最新可用版本。
- /rule-library及旧/local兼容选项接口都只返回已上传包；POST登记兼容端点只定位已有上传包，不再登记local://。前端上传和Skills共用数据库目录，移除本地登记按钮；缺包时提示先发布。
- 旧local://记录及项目FK不改，项目元数据按原ID读取；旧冻结包继续服务原项目。当前任务不迁移项目、不删除旧引用/Storage。
- 本地版本与数据库local://版本冲突时，为ABB/XMZ生成补丁发布版本1.3.1/0.2.1；ZH为2.3.0。提取Prompt/Expected/图像/规则配置保持原内容，只更新包身份版本，不绕过不可变版本发布RPC。
- 使用现有publish_extraction_profile和内容寻址Storage协议；不新增迁移或业务字段。先完成包及调用链验证，再显式apply上传并逐包读回校验。发布现有Auth所有者为已有三套规则的同一所有者。

## 执行计划

1. 已完成：数据库目录/界面适配及可重入上传工具，三套包dry-run通过。
2. 已完成：类型/lint/build、3源码mypy、离线API及隔离界面通过，11截图覆盖桌面/窄屏与空态/失败/权限/旧项目兼容。
3. 已完成：三包已上传/登记并读回，15组消息相同，原6条规则记录和项目绑定/线表版本摘要不变；文档已更新，8000由用户重载。

不自动重启用户服务，不调用真实模型或创建提取任务。规则包不包含可执行Python，Worker仍提供已有注册adapter。
