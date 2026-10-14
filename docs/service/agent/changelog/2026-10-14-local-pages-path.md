# 本地拆分页目录引用更新

用户将拆分页移动到docs/test/pages。run_stage2_groups.py默认--pages-dir改为docs/test/pages；在实际新目录中找到索引agent/drawing_index.json，因此--index默认值同步为docs/test/pages/agent/drawing_index.json。

页面定位仍根据功能区/业务页码/PDF物理页号从传入pages-dir构造实际图片路径，不依赖索引里可能保留的旧PDF路径。其余参数、提取实现、Profile、内存/数据库隔离和输出目录不变。测试说明同步。

本轮只读确认目录与索引位置，没有执行测试脚本、真实模型、数据库/Storage操作或覆盖结果。
