# 已发布规则显示名称编辑

新增PATCH /api/v1/rule-library/{profile_id}，Pydantic输入display_name和expected_display_name，仅创建者可改已上传目录行，按id/owner/旧名称进行条件更新，重复目标名幂等。返回can_rename供界面使用，list同步该计算权限。业务Model/OpenAPI/TS已同步。

只更新extraction_profiles.display_name。profile_key、版本、checksum、resource_ref、不可变ZIP及项目/任务冻结绑定保持。名称为目录显示名，包内profile.json仍保留发布时原值。无Storage修改或新迁移。

5项Server离线回归通过，验证鉴权、恶意多余字段、空白/长度、冲突、更新竞争、幂等、被项目引用时仍可改名且其他表不变，无Storage请求。16项浏览器、类型/lint/build、Ruff/3源码mypy与截图通过。未改任何实际规则/业务库或启停服务。需重载8000并刷新前端；8100不改。设计见[目录名称](../profile-display-name.md)。
