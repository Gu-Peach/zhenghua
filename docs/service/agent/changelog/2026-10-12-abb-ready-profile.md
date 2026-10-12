# ABB 1.1.2 可用 Profile

日期：2026-10-12。

## 实现

- 注册 `abb_native` 三阶段 VLM adapter，使用 ABB 包内 Prompt/Few-shot；Stage 2 不包含 ZH XD 起点白名单。
- 新增 ABB 确定性 policy：Sheet/Cont 页面身份、`/Sheet.列行` 引用解析、唯一目标页定位、保守方向/电流/字段校验和预处理导出。
- 本地 Profile 更新为 active 1.1.2，并声明 `full_document_extraction`。
- 18 文件包上传私有 `agent-profile-assets`，ID `2ea7b54a-50c5-5ead-8449-25fea2cb79ba`，checksum `sha256:0f44b0382bd9c409ea328e9dc4d0fcee3ffffdb98f265e27f4800c374372444e`；逐文件下载验证通过。
- 上传入口重命名为 `scripts/upload_profile_package.py`，不再使用 draft 命名。
- 远端 Registry 只为新任务选择每个 key 最新 active 包；1.1.0/1.1.1 及冻结运行 checksum 保留。

## 验证边界

Fake Model 覆盖 ABB Stage 1/2/3 分派、元数据和 ZH 指令隔离；策略测试覆盖 241 Sheet 到 PDF 2/LV12 的唯一解析。Agent 全套默认测试和 strict mypy 通过，未调用真实模型。ABB 当前是“可执行”，真实字段准确率、耗时和费用仍需人工固定案例验收。
