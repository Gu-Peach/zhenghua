# 002.C shared wiring example

This directory is the active image-backed Few-shot package for Stage 2 and Stage 3.

- `images/` contains the five canonical drawings once.
- `stage2/*.expected.json` contains single-page `PageScanResult` answers.
- `stage3/*.task.json` is the exact Stage 3 `task_context` input.
- `stage3/*.expected.json` contains the matching `CrossPageCompletion` answer.
- `manifest.json` exposes `stage2_cases` and `stage3_cases` to their respective loaders.
- Stage 3 selects one relevant case per terminal task; each example contains one target page image and a JSON task context with the source-page metadata.

Stage 2 coverage:

- `002.C/3`: allowed starts and same-page endpoints; device location references are not cross-page wire references.
- `002.C/6`: negative source-page example; it is a valid Stage 3 target but has no allowed Stage 2 start terminal.
- `002.C/11`: XA completeness and breaker `Ir` current evidence.
- `002.C/21`: true cross-Plant-Function references.

Stage 3 coverage:

- `002.C/11 -> 002.C/6`: same-function cross-page completion.
- Stage 3 的当前案例验证：来源页已有 `Ir=400A` 时，目标页只补全终点，不能覆盖已有电流。
