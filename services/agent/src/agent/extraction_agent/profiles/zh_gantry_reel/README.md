# zh_gantry_reel

`profile.json` / `rules.json` 为独立本地实验入口，适配器 `zh_gantry_reel_native`，版本 0.1.1，Prompt资源目录采用`xmz`。

资源详见 [Prompt README](../../prompts/xmz/README.md)。共享 ZH 的稳定 JSON/图像请求、结构化Schema与电流证据校验；初扫从放线斜杠找最近端子。页标/引用策略独立；模型terminal_strip为空，由程序读取实际X排号，不使用旧 XA/XD 分类映射。expected只读取配套图片，不使用人工XLSX补字段。

只有显式 `allow_experimental=True` 时可绑定。新资源没有上传私有 Bucket/数据库，不改变已有项目版本。页标使用可逆规范键，原始 SH.NO. 始终保留；实验 expected 尚待工程人员确认及真实模型回归。
