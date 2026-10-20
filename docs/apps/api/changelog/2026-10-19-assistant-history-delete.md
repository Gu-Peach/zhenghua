# API2.13.0：主助手历史删除

新增 `DELETE /api/v1/assistant/conversations/{conversation}`，返回204空响应；UUID路径、JWT身份和所有者校验由现有入口处理，删除/附件清理属于Server application service。OpenAPI与Web生成类型同步。

Server默认107项、临时SQL2项和Web12项通过；当前本地API已加载2.13.0。见[Server记录](../../../service/server/changelog/2026-10-19-assistant-conversation-deletion.md)。
