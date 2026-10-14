# ZH离线样例清理

按用户明确要求，删除manifest中的regression_cases、regression目录两份C05/M01局部expected，以及仅该组使用的002c05.png/002m01.png图片。原始docs/test拆分页不变。

同步manifest v5的图片索引、quality-provenance资源条目、README及smoke文件中的相关读取/断言；不让测试继续引用已删除文件。当前工作区已有的实体stage3历史文件删除保留，不恢复。

运行时仍是5组stage2_cases和2组stage3_cases（后者指向completion），初扫/补全Prompt和加载代码未变，本地ZH版本仍2.0.2。资源目录内容变化会改变本地Profile摘要。

本轮未运行测试、提取脚本或真实模型，未写数据库/Storage、发布规则、重启服务或覆盖旧结果。只做文件与引用清理，不声称测试或准确率已通过。
