# 导航居中与表格内编辑

日期：2026-10-13。

## 改动

- `assets/styles.css`：资源导航、搜索使用等宽左右轨道，相对各自容器水平居中；项目名保持左侧、上传/新增保持右侧。窄屏导航/搜索置独立居中行。
- `apis/connection-fields.ts`：维护可编辑字段、最大长度、共享字段信息、初始值及差异 DTO；清空保存为 null，未变化字段不提交。
- `components/ResultTable.tsx`：双击可编辑单元格或行编辑按钮原位输入；Enter/勾选保存本行、Esc/叉号取消、Tab 移动。页码/线号只读；共享字段语义提示，保存状态和错误在表格内显示。
- `views/ProjectView.tsx`：停止调用 ConnectionEditor 弹窗，复用现有 projectApi.edit；保存回调在开始编辑时冻结版本上下文。后台重读时保留 ResultTable 挂载，不替换草稿；切换范围/分页时重建编辑上下文。成功响应后刷新真实分页数据。

相同草稿重试复用 Idempotency-Key，防止响应丢失时重复修订。服务端拒绝旧 revision/record_version 时保留用户输入，支持取消编辑并刷新。记录消失时有退出编辑入口。没有新增 API、Schema 或改变 Server 修订事务。

## 验证

- Web typecheck/lint/production build 通过。
- `workbench.spec.ts` HTTP fixture：16 项通过，包含对容器中心误差不超过 1px 的检查、原位 Enter/Esc/Tab、只读线号、仅变化字段、空值、失败草稿和同 key 重试；后台更新后仍提交旧基线并收到 409，取消刷新后看到最新数据。
- 原跨页下方预览、图片目录、上传类型确认、纠错确认及悬浮聊天续传回归通过。
- 检查 `.runtime/web-tests/inline-edit-*.png`、工作台、登录及资源界面桌面/390px 窄屏截图；输入框/按钮可见，横向列滚动留在表格内，页面无横向溢出。

本轮使用 HTTP fixtures，未修改真实数据库或调用真实模型。刷新开发前端即可使用新交互。
