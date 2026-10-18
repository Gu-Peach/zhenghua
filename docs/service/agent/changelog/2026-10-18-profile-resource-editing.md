# Profile现有规则编辑

2026-10-18，见[ADR-0032](../../../adr/0032-profile-resource-editing.md)和[执行计划](../profile-resource-editing-plan.md)。

复用ProfileAgent工具Graph，增加ProfileEditor和可信ProfileImport：校验Storage ZIP库存、路径、摘要和来源身份后派生patch版本草稿，也支持已登记本地资源；Source记录规则ID、版本和摘要。草稿的双击保存和模型建议确认共用DraftStore修订/文件摘要/原子保存与审计；手动编辑保护身份、Schema和公共约束。未修改的样例继承人工基线，用户明确确认当前修改及Expected后方可发布。

编辑入口仅允许讨论/提建议，提供read_file、view_images、record_diagnosis、propose_edits等现有工具；模型不能自行确认或发布。ProfileTurn新增本轮图片ID及关注阶段，首轮自动加载最新规则和代表少样本，当前图优先，缺证据及截断显式说明。用户的实际提取结果作为observations，并与图片ID一起保存到对话历史，不自动作为Expected。建议包含精确before/after、来源修订及证据；确认后应用，相同操作幂等，过时建议拒绝。

只读预览和编辑包正文分离；Schema由代码维护，旧ZIP验证后仅在新草稿内兼容升级、同步模板版本，并提示核对；不改原包。恢复时若协议更新，产生修订并重新核对。新增编辑状态、保存、人工核对、导入等接口，现有创建向导/SDK保留；Server生成DTO及OpenAPI/TS已同步，创建草稿列表不混入编辑草稿。

验证：76项Profile相关Agent离线用例覆盖（75项组合回归及最终4项编辑复验通过），包括Storage导入、手动保存/审核/导出、工具提案/确认、越权/摘要冲突/保护文件、旧Schema兼容；原SDK、向导、聊天和PDF抽样保留。另有26项Server、2项独立SQL和59项浏览器回归，类型/Ruff/11源码mypy及前端lint/build通过。没有调用付费模型、修改实际用户草稿或发布真实规则；模型的真实诊断质量需用户试用。

另只读下载真实已发布ZIP，在自动清理的临时目录验证导入：生成1.0.1草稿，4个既有样例通过校验，旧Schema兼容升级提示正确。原ZIP/实际草稿/业务库没有被编辑，Fake网关调用数为0。运行服务仍未加载imports/编辑代理，用户需重载8000和8100；其他线程的提取入口/Schema改动已保留。
