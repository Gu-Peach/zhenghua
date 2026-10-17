# 规则草稿创建404排查

2026-10-17。用户点击新建草稿，页面保持表单并显示Not Found。

只读查询运行服务OpenAPI：8000为Wiring Workbench Server 2.2.0，未包含任何`/api/v1/profile/drafts`路由；8100已有`/v1/profile/drafts`及向导接口。当前`apps/api/src/main.py`为2.3.0且安装profile_routes，前端请求与源码路由一致。失败原因是8000进程未加载新增接口，请求未进入Agent。

解决方式：由用户在原终端停止并按原命令重新启动8000，然后刷新规则创建页。新服务OpenAPI应出现`/api/v1/profile/drafts`。不需要修改现有前端或Agent路由。

离线验证：`python -m pytest services/server/tests/test_profile_authoring_api.py -q`共3项通过，包含Mock鉴权代理、草稿创建/阶段确认/发布与目录预览；出现Starlette弃用和pytest缓存权限警告，不影响通过结果。未运行真实模型、创建真实草稿、写业务数据库或启停用户服务。真实界面重试留待用户重载8000后进行。
