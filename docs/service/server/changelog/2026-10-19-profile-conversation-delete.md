# 规则会话删除接口

新增 `DELETE /api/v1/profile/drafts/{draft}`，请求 `DraftDeleteInput { revision, confirmed: true }`，成功204无响应体。登录身份由Server转为内部受信头，用户不能通过请求体指定所有者。403/404/409透传稳定错误，确认缺失/为假或多余字段返回422。

AgentBridge支持204空响应，避免成功删除后被JSON解码误报失败。规则包、数据库目录和项目绑定不受会话删除影响。

4项隔离API回归覆盖鉴权、伪造所有者、确认参数、空响应及三类Agent错误，业务表夹具摘要不变；5源码mypy、Ruff、契约导出与前端检查通过。未访问真实业务库、删除真实会话或启停服务。启用需重载8000与8100并刷新Web，无新迁移。见[设计](../../agent/profile-conversation-management.md)、[Web交付](../../../apps/web/changelog/2026-10-19-profile-conversation-controls.md)。
