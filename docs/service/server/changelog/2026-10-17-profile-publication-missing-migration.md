# 发布失败：本地缺少发布迁移

2026-10-17。用户已完成三阶段确认，点击发布出现“数据操作失败”。只读核对确认：规则ZIP已上传私有Storage且与Agent导出摘要一致，但本地库不存在`public.publish_extraction_profile(uuid,text,text,text,text,text)`，也没有`20261017010000`迁移登记。包生成/上传与规则登记是不同步骤；统一Repository把缺失RPC的PGRST202隐藏成通用错误，导致界面无法判断部署缺口。

## 已处理

- 在独立无网络/无业务卷临时PostgreSQL容器重跑既有迁移的空库/旧数据、权限、幂等与不可变版本测试，通过后清理临时容器。
- 原样应用已审阅迁移`supabase/migrations/20261017010000_profile_wizard_publication.sql`到明确的本地`supabase_db_zhenghua_test`，单事务新增发布RPC/保护触发器、授权并登记迁移；没有修改旧迁移内容或直接插入用户规则。
- 部署前后核对项目、连接行、规则和Storage对象摘要一致。验证service_role可执行、authenticated/anon不可执行；迁移内通知PostgREST刷新Schema，REST OpenAPI只读检查已可见发布RPC。
- 只读下载先前上传包核对摘要，确认当前草稿对应规则仍未登记。用户直接再次点击“发布规则”即可复用已有包并登记，无需重做三阶段；未代为重试发布或启停8000/8100/Worker。

Repository将缺失RPC分类为`DATABASE_FUNCTION_MISSING`，只记录错误码/函数名，不输出原始数据库消息或请求凭据。发布Service转换为`PROFILE_PUBLICATION_NOT_READY`和明确的迁移/Schema缓存提示；既有内容寻址上传及失败后重试复用逻辑不变。错误提示代码需下次加载8000后生效；本次数据库部署补齐已生效，重试发布不依赖重新加载服务。

## 验证与边界

26项Server发布/代理/数据管理Mock回归及2项独立SQL集成通过；新增复现覆盖缺函数的安全错误分类、未登记不显示成功，以及补齐后复用相同已上传包。Ruff、2源码mypy和diff检查通过。公共DTO/接口形状未变，不重新生成Client；前端代码未改。

真实本地部署只执行迁移DDL/历史登记和只读检查，不调用真实发布RPC、不调用模型、不写入新的用户规则记录。用户规则最终发布尚待界面重试。私有部署摘要在忽略目录`.runtime/profile-publication-check/deployment.json`，运行脚本/导出包和用户标识不提交。
