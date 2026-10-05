# Few-shot 示例图纸

这里保存线表提取的多模态 few-shot 案例：示例图纸图片 + 标准答案 `expected.json`。

后端默认启用多模态 few-shot（`VLM_FEW_SHOT_IMAGES=true`）：每次提取请求会按 `manifest.json` 依次插入“用户轮（示例图纸）→ 助手轮（expected.json）”，最后才是当前任务图片。设为 `false` 可关闭；`VLM_FEW_SHOT_EXAMPLES_DIR` 可指向其他示例目录。

`expected.json` 的格式以 `backend/app/cases/Validation/*/result.png` 为准：起点端子写 `XD3:251`，端子排写归一化后的 `X3`，终点端子按设备侧原样写（`X3:3`、`2-RED`），SPARE 芯端子为 `*`，PE 芯端子为 `PE`。

## 案例

- `006m01_006c01/`：示例 1，006M01 起点页 + 006C01 终点页（跨页），`expected.json` 12 芯。
- `082r50/`：示例 2，082R50 单页，`expected.json` 7 芯。
