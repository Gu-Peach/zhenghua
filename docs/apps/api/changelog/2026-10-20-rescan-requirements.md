# API2.14.0 重扫需求契约

RescanRequest新增可空requirements：required_fields限定start_terminal/end_terminal/principle_number，expected_start_terminals保留预期集合，connection_set为preserve/rebuild，endpoint_location为unspecified/same_page。历史请求和任务可缺省，公开响应可读；新Explain模型工具要求四项显式给出并在Agent端校验能力/范围。

Agent模型通过export_explain_contract.py生成Server DTO，再生成apps/api/openapi.json与Web类型；两侧Schema一致。沿用原request JSONB、路由和确认事务，无migration。模型无法直接指定删除模式，正式写入仍由已有候选确认接口执行。

本轮API版本2.14.0。46项相关Server测试及契约往返通过，16项显式SQL集成默认跳过；未操作实际业务库。先重载8000，再加载8100/Worker并刷新Web。完整路由与验收见[Agent交付](../../../service/agent/changelog/2026-10-20-rescan-requirements-routing.md)。
