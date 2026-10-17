# 补全聊天回到初扫修正候选

2026-10-17。Agent返回的现有ConversationState支持阶段回退，前端沿用apply逻辑自动选中第二阶段，展示纠正后的起终点和确认入口，不重复上传原图。分类确认保持，旧补全确认不会误显示为已完成。同页候选确认后明确无需这条连接的目标图。

没有新增前端生产接口或字段。新增浏览器夹具模拟同页纠正回退，11项规则聊天回归通过；核对阶段、原图上传次数、修正端点、重新确认和第三阶段未被自动确认，TypeScript/lint/build通过。桌面截图在`.runtime/profile-clarification-check`。Agent改动见[记录](../../../service/agent/changelog/2026-10-17-profile-repeated-clarification.md)。
