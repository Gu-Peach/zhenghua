# zh_crop：本地局部高清实验

显式使用--profile zh_crop加载2.2.0 experimental规则；原--profile zh仍加载2.1.1并使用整页。初扫Prompt、规则、1组初扫/5组补全原始案例与基线复用，不重新扩展样例。

仅跨页补全按唯一有效列号裁原始目标图的全高窄带，左右保留0.95列余量。图框约定为0～9列，列号缺失/冲突/越界或宽高比不支持时调用前回退原图。不会另调模型定位，也不为视图外未确认线路自动再调模型。

实际局部图像素不超过同一原图按原2048长边发送时的像素；只允许局部图最长边达到规则上限4096，不增加总像素预算。服务端可能再处理图片，实际token与精度待用户测试。

坐标按当前输入图归一化，由程序映射回原始整页；裁剪框只在程序/日志中，模型只收到image_view模式和列号。Few-shot临时裁剪并转换expected点，不改原图/原始expected。所有图像在内存处理，32项缓存按原图属性及规则/预算隔离。

completion_view.json的enabled可关闭裁剪进行对照；completion_view.provenance.json记录源文件摘要。2026-10-17已按用户要求解除源码和配套测试/文档的本地忽略与提交拦截，可随当前版本提交；仍为显式选择的experimental规则，不代表生产发布。测试结果、缓存和模型日志继续忽略。

在仓库根目录用新目录测试（脚本仅使用内存及本地文件，不上传数据库）：

```powershell
.\.venv\Scripts\python.exe services/agent/scripts/run_stage2_groups.py `
  --allow-real-model `
  --profile zh_crop `
  --model "Qwen3.8 27B" `
  --groups 003.C 004.C `
  --output-dir docs/test/run_stage2_crop_001 `
  --run-id stage2-crop-001
```

输出result.xlsx保持14列及原图归一化坐标；调用日志的completion_image_view用于查看裁剪框或整页回退原因。不要复用旧运行目录进行新旧规则对比。
