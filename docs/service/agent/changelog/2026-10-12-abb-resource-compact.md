# ABB 1.1.1 精简样例

> 后续状态：样例继续由 1.1.2 使用；旧不可变包保留，并由共享规则 migration 标为 active。见 [1.1.2 记录](./2026-10-12-abb-ready-profile.md)。

日期：2026-10-12。按用户要求替代本地 1.1.0 多案例资源；旧 Bucket 包保持不可变。

| 阶段 | 案例数 | 图片 | 内容 |
| --- | --- | --- | --- |
| Stage 1 | 1 | Sheet 205 | 页面身份 LV11/205，排除 Cont 206 |
| Stage 2 | 1 | Sheet 205 完整原页 | Q4:2/4/6/8 跨页出线到 241 |
| Stage 3 | 1 | Sheet 205 原页 + Sheet 241 目标页 | Q4 L1 到 +EH.Q21-Q1:2，起点冻结 |

Stage 2 的图片为完整页，但 expected 仅示范 Q4，manifest、Prompt 和 warnings 明确它不是整页穷举答案。真实扫描范围仍为所有符合放线规则的连接。Stage 3 示例两张图分别标记 source_page/target_page，不改生产工作流输入或冻结起点契约。

已删除本地样本目录中的额外 expected/task、无用页副本与裁剪副本；保留用户原始 1.png～4.png。同步修改 manifest、provenance、README、CHANGELOG、图片复现脚本和现有资源测试。Profile 版本更新为 1.1.1，保持 experimental/draft。

## 实际上传

- Bucket：agent-profile-assets（私有）。
- Package ID：2f19853f-ca15-5fd5-9781-7bb0e2a58270。
- 前缀：abb/1.1.1/c21583d32c2cba57fe107091e17e8c047f5739b788fae3ba29c85b7de1c3e12d。
- checksum：sha256:c21583d32c2cba57fe107091e17e8c047f5739b788fae3ba29c85b7de1c3e12d。
- 18 文件全部下载读回核验通过，包内 3 个 PNG 文件（分类原页一份、线表原页/目标页共享）。

11 项 ABB/Registry/Router 离线回归与修改脚本/测试 Ruff 通过。未调用真实模型、重启服务、改变 test0/项目绑定或发布 active 包。工程确认、ABB 独立确定性策略和真实图片模型回归仍未完成。
