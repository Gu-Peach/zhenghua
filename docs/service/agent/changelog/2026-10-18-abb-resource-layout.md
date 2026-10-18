# ABB资源名称统一到ZH

2026-10-18，本地资源包`abb@1.2.2`。用户要求目录/文件旧名称也对齐ZH，本轮只迁移资源与引用，保留1.2.1识别规则和输出。

| 原位置 | 现位置 |
| --- | --- |
| prompts/abb/page_cross_page_completion.md | prompts/abb/page_connection_completion.md |
| prompts/abb/examples_wiring/annotated | prompts/abb/examples_wiring/lv11 |
| 样例stage3目录 | 样例completion目录 |
| 样例provenance.json | 样例quality-provenance.json |
| 样例offline_manifest.json与三份未生效Expected | services/agent/tests/fixtures/abb_reference/manifest.json与stage2目录 |
| prompts/abb根目录1/2/3/4.png | 测试夹具images/lv11_205、lv12_241、lv21_281、cv09_432.png |

当前样例目录与ZH采用相同结构：images、stage2、completion、manifest.json、quality-provenance.json、README.md。历史281图片从运行包移出，其原图与离线夹具完整保留；离线manifest共享的补全task/expected也保留副本。重复281图经字节比较后合并，不丢失唯一图像内容。为迁移后的四张原图增加窄范围.gitignore例外，避免丢失版本化测试资产。

Profile资源引用、manifest相对路径/摘要、质量来源、图片准备脚本、两份测试文件引用均已更新；图片脚本只复制生效205/241与分类图片。包版本改为1.2.2，识别Prompt版本保留1.2.1，内容逐字节不改。公共manifest键stage3_cases也被ZH使用，保持加载协议不改；物理目录统一为completion，不代表存在独立Stage3。不额外添加内容重复的crop Prompt，ABB目标局部图配置继续使用。

静态结果：3个Python文件AST/Ruff通过，ABB1.2.2绑定有效；当前一例初扫（27条连接）和一例补全可加载并通过Pydantic；16项manifest文件引用、44项摘要通过，17份Prompt/图像/Expected与迁移前字节一致。ZH/XMZ无改动，命令参数、模型图片数量和内容、Graph、十四列输出/空色标及坐标机制保持。

未运行测试套件、Fake VLM或真实模型，未改运行结果、数据库、Storage或已发布规则；用户继续原脚本以新输出目录测试。当前用户其他未提交Explain改动保留。历史设计/发布记录中的旧名称表示当时路径，不回写历史。
