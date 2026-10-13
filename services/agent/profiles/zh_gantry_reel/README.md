# zh_gantry_reel

`profile.json` / `rules.json` 为独立本地实验入口，适配器 `zh_gantry_reel_native`，版本 0.1.0。

资源详见 [Prompt README](../../prompts/zh_gantry_reel/README.md)。共享 ZH 的稳定 JSON/图像请求设施与电流证据校验，模板指令、页标/引用和实际端子策略独立；不使用旧 XA/XD 分类映射。

只有显式 `allow_experimental=True` 时可绑定。新资源没有上传私有 Bucket/数据库，不改变已有项目版本。页标使用可逆规范键，原始 SH.NO. 始终保留；实验 expected 尚待工程人员确认及真实模型回归。
