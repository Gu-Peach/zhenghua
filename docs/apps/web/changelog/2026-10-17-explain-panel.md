# 独立来源解释浮窗

2026-10-17。依据：[ADR-0025](../../../adr/0025-explain-panel-integration.md)。

## 行为

线表起点端子单元格悬停/键盘聚焦显示解释图标；页码组首图标解释本页所有端子，触屏直接显示。保留原单元格无障碍名称、双击编辑及跨页图纸交互。新增ExplainPanel，不复用旧FloatingAgentPanel；打开时暂隐藏旧主助手入口，关闭后恢复。

点击即创建独立会话并自动提问，显示执行状态、流式公开回答和淡色可展开工具记录；展开后可查看匹配连接、原页/跨页、缺口和完整工具结果。图纸以独立区域展示并可打开原图；缺图/签名过期可见。支持追问、停止、同turn重试、Escape关闭、焦点返回入口、卸载取消和项目隔离。缺历史依据不冒充历史推理。

API/DTO转换位于apis/explain.ts，流状态位于useExplainConversation，后端事件来自生成TypeScript；不在组件散落请求URL。浏览器只请求8000，后端代理共享8100。无需数据库迁移。

## 验证与限制

新增7项真实浏览器/离线HTTP和分段SSE用例，连同15项既有工作台回归共22项通过。覆盖自动请求、部分回复先到、工具展开、原页/跨页、页筛选参数、追问、403/重试、关闭断流/新会话、停止、长文本与缺图。typecheck、ESLint和production build通过。

登录和工作台桌面/390px窄屏截图已检查。新增截图位于被忽略的.runtime/simple-management-browser目录（explain-row-desktop、explain-loading-desktop、explain-denied、explain-narrow-long、login-desktop、login-narrow），不提交测试产物。没有接触真实数据库/模型、写数据或重启现有服务。

使用前需加载8000 API 2.2.0与8100的src.extraction_main；仅启动提取Worker不足以提供Explain HTTP。真实模型工具/视觉质量与实际数据联调尚未运行；聊天为有界短期会话，关闭后重新打开新会话。启动说明见[Web README](../../../../apps/web/README.md)。
