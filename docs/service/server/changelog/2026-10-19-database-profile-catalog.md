# 数据库规则包作为运行目录

## 已发布资源

2026-10-19按用户明确授权，将完整ZIP上传到当前本地项目的私有project-assets，并通过既有publish_extraction_profile登记extraction_profiles：

| 规则 | 数据库版本 | 来源本地版本 | 数据库ID |
| --- | --- | --- | --- |
| ZH | 2.3.0 | 2.3.0 | 88d1d0fa-77d0-46c0-88ea-0e75d12438d9 |
| ABB | 1.3.1 | 1.3.0 | ecb1672a-edce-4515-b238-e78aad856b8e |
| XMZ（zh_gantry_reel） | 0.2.1 | 0.2.0 | b91301f3-0f3b-495b-850d-c01a997da6eb |

ABB/XMZ已有同版本local://记录，因此采用补丁发布版本保留旧项目绑定，未修改其提取资源。包身份版本/可用状态变化，Prompt、图片、Expected、引用和裁剪配置保持。三包38/24/32份清单文件，完整读回和摘要校验通过。

## 行为

- ProfileReferences.list/available仅返回有效Storage引用的已上传数据库记录，每key选最新包；不会合并本地catalog，即使本地有更高版本也不会加入列表。
- 旧/local选项URL保留兼容但数据来自同一数据库目录；POST登记端点仅查找已有包，无包返回PROFILE_NOT_AVAILABLE。新建项目/上传不再接受仅本地引用。
- 前端上传PDF和Extraction Skills共用/rule-library数据；额外过滤旧API返回的local://记录，移除本地登记UI。无包时提示先发布；已上传自定义包仍正常展示。
- 旧项目元数据按原profile_id读取，保留全部旧引用和原冻结包。没有删除旧版本、GC包或迁移项目绑定。

## 校验

离线真实路由/Mock数据库验证目录不读本地、较高本地版本不能覆盖数据库包、缺包不回退、旧项目可读、非法本地选择不产生项目/任务。前端隔离HTTP夹具覆盖Skills/真实包预览/选择、空态、加载、失败、无权限及桌面/390px窄屏，含登录共11截图。

真实只读核对数据库目录为ABB1.3.1、ZH2.3.0、XMZ0.2.1和原已上传自定义包1.0.0；三包可独立加载，15组Few-shot消息构造与本地相同。原6条规则记录逐字段不变，项目绑定/线表版本摘要在发布前后相同。未运行pytest、Fake VLM、真实模型或提取任务。

Ruff/AST、3源码mypy与前端类型/lint/build通过。公开API字段/DTO未改，保留既有响应Schema与路径，无需迁移或生成新客户端。流程和版本边界见[ADR-0037](../../../adr/0037-database-profile-catalog.md)。

## 启用与后续

用户重载8000 API并刷新前端以启用服务端数据库唯一目录；既有Worker已支持Storage包，不新增Worker服务或自动重跑任务。本轮未启停用户服务。

管理工具 `services/agent/scripts/bootstrap_database_profiles.py --owner-id <已有所有者UUID>` 默认仅准备包和只读预检，显式 `--apply` 才上传/登记。当前三套源/目标版本映射是本次初始化用途，后续修改应通过规则编辑/发布新版本；不能用修改本地文件悄悄覆盖已发布包。

操作回执、只读检查和截图位于忽略的 `.runtime/profile-catalog-upload/`；工具使用内容寻址、确定性ZIP及不可变发布RPC，失败可重入，首次before快照保留。旧legacy上传脚本仍用于原控制面，本次使用的是业务表extraction_profiles/project-assets协议。
