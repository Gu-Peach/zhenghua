# 整份PDF遍历结束即处理完成

按用户2026-10-18的明确要求，处理完成表示整份PDF工作流遍历并正常收尾，后续结果由用户自行校验。此约定替代同日早期“仍有单页错误则整任务失败”的汇总策略。

## 实现

- `incremental_worker.execute_job` 在文档工作流正常返回后统一提交 `finished`。页错误清单和数量放入完成产物metrics，保留本地诊断和逐页失败尝试；不再提交 `EXTRACTION_PARTIAL` 失败事件。
- 现有SQL将 `finished` 对应项目置为 `ready`，前端显示“处理完成”。内部行/页复核信息及run的 `NEEDS_REVIEW` 语义保留，不将未知字段标成已确认。
- `apps/web/src/apis/projects.ts` 兼容旧Worker生成的 `failed + EXTRACTION_PARTIAL`：该聚合码仅在整份文档遍历后产生，统一映射为完成。当前已跑完的历史部分失败项目刷新前端即可显示完成，不重跑提取或改历史数据库。
- 配置、权限、持久化、租约或其他异常导致文档未正常返回时，仍通过原异常处理显示失败。处理中和归档状态不受兼容映射影响。

模型请求、Prompt、Profile业务版本、Schema/API字段和数据库结构均未改变。3份运行来源摘要同步更新Worker文件哈希。

## 验证与启用

2文件Ruff/AST、Worker定向mypy、前端TypeScript/lint/生产构建及diff检查通过，98项运行来源摘要无失配。完成回归代码覆盖有/无页错误的正常收尾，未运行pytest、Fake VLM或真实模型。

隔离HTTP夹具浏览器核对旧部分失败、正常ready、真正中断、处理中、空表与登录；5份桌面/390px窄屏截图保存在忽略的 `.runtime/extraction-finished-check/`。真正中断仍保留失败提示及重试按钮。窄屏按原布局隐藏顶部状态标签，检查其DOM状态及页面提示。

未操作现有任务、真实数据库、Storage或用户服务。当前页面刷新即可使用兼容显示；后续执行需由用户重启实际提取Worker加载新收尾逻辑。后端/API无需因本改动部署或迁移。
