# ABB历史图像与离线夹具

2026-10-18从原ABB Prompt资源目录迁移而来，避免历史案例混入生效Profile包。当前提取入口在src/agent/extraction_agent/prompts/abb/examples_wiring/lv11。

- images保存用户提供的四张原图，按业务页命名：原1.png→lv11_205.png、2.png→lv12_241.png、3.png→lv21_281.png、4.png→cv09_432.png，图像字节不变。
- stage2保存三份历史Expected；completion保留历史manifest当时所引用的task/expected副本，文件字节不变。旧manifest改名为本目录manifest.json并更新相对路径，不参与运行时模型请求。
- 281小圆圈夹具仍供离线资源检查引用。图片准备脚本从这里读取205/241原图以复制当前样例和分类图片。

这是一份版本化测试资产目录，不是模型输出或运行日志；与当前提取规则不一致的历史答案不能作为运行时Few-shot使用。

1.3.0新增current-regression.json及三份.current/receivers.expected.json，作为281实际编号/针脚、432同段追踪和241接收端的当前字段参考；这些正/负聚焦案例不同于上方历史manifest，不增加模型Few-shot图片。坐标为图像目视近似，待工程验证；本轮未执行回归。
