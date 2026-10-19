# 振华正式提取规则 zh@2.3.0

本版本整理自用户已验证的 `zh_crop@2.2.1`。初扫、分类、局部补全Prompt，案例图片/Expected/任务输入及局部裁剪配置逐字节沿用；只调整规则身份、资源位置与正式入口，不重写提取算法。

## 目录

- `profile.json`：正式身份、版本与指向 `../../prompts/zh` 的本地资源引用。
- `rules.json`：阶段资源及业务约定，沿用已验证的目标图补全模式。
- `completion_view.json`：0～9列网格、0.95列余量、最长边4096的目标局部视图配置。
- `completion_view.provenance.json`：资源与运行代码来源摘要。
- `../../prompts/zh/`：唯一维护三阶段Prompt、2个分类案例及1个初扫/7个跨页案例，含真实图像与Expected；源码目录不再保存resources副本。
- 根目录Python：部署端 `zh_native` 的索引、引用、归一化、端子排和校验策略。XMZ仍复用其既有继承路径。

## 使用与上传边界

新处理选择“振华电气图纸 · 2.3.0”，脚本使用 `--profile zh`。zh_crop目录已由用户移除，新调用统一使用zh；已有任务使用自己的冻结包，不自动迁移。

规则资源包只包含manifest、Schema、配置、Prompt与案例等资源，部署环境必须已有 `zh_native` Python策略。通过 `src.profiles.package.build_package` 收集manifest声明的外部资源，在生成包内建立自包含resources；本地不需要维护第二份副本。本次只生成本地校验包，没有上传或写数据库。

本地阶段测试命令保持，只将profile参数改为zh并使用新输出目录：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --allow-real-model --profile zh --model "Qwen3.8 27B" `
  --groups 003.C 004.C --output-dir docs/test/run_zh_230_001 --run-id zh-230-001
```

目录整理不代表额外真实模型评测；本轮仅做资源、Schema、消息构造和打包校验，不运行模型/测试或操作既有任务。
