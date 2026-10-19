# 引导式规则配置契约

公共PDF抽样端点保持不变，请求stage支持classification/scan/completion，PdfSampleInfo新增缺省classification的stage。StageGenerate.sample_images上限从2扩大到4。Agent DTO经生成同步Server、OpenAPI及TypeScript；无路由/身份边界或业务表变化。

5项接口回归通过，Agent/Server模型Schema一致；未确认分类时上传scan PDF返回409 PREVIOUS_STAGE_REQUIRED，所有者、内部凭据、幂等抽样和未保存原PDF仍受校验。新上传PDF只使对应阶段及后续失效，不改前序确认。

未访问真实业务库或模型、未发布规则、未启停服务。需8000和8100同时加载本次契约，再刷新Web；无需迁移。见[Agent交付](../../agent/changelog/2026-10-19-guided-profile-authoring.md)与[ADR-0038](../../../adr/0038-guided-profile-authoring.md)。
