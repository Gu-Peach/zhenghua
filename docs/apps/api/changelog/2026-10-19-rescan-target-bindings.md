# API2.12.0：重扫目标绑定

RescanRequest新增target_bindings，生成Server/OpenAPI/Web类型同步；默认空列表兼容旧请求，仅用于终点重扫。无路由/鉴权/数据库Schema变化。见[Server记录](../../../service/server/changelog/2026-10-19-rescan-target-contract.md)。需重载8000及Agent/Worker，旧任务不修改。
