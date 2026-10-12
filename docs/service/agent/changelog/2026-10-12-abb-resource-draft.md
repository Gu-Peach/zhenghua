# ABB 1.1.0 图片样本资源草稿

> 后续状态：已被 1.1.2 可用 Profile 取代；旧不可变对象保留，并由共享规则 migration 将手工包标为 active。见 [1.1.2 记录](./2026-10-12-abb-ready-profile.md)。

日期：2026-10-12。任务范围为用户提供的 `services/agent/prompts/abb/1.png`～`4.png` 整理与私有 Bucket 上传。

## 样本与规则

保留原图，新增独立 `page_classification.md`、`page_scan_index.md`、`page_cross_page_completion.md`。目录格式与 ZH 一致，包含图片、manifest、expected 和跨页 task；不复用 ZH XD 起点白名单。

- Stage 1：四张整页图，LV11/205、LV12/241、LV21/281、CV09/432。Sheet 是当前业务页号，Cont 是后续引用，不能混用。
- Stage 2：四个局部裁剪案例，覆盖 Q4 跨页输出、Q50 内接线负例、X1 外接线正例和 X3 同段数字原理号案例。expected 只覆盖标明的裁剪范围。
- Stage 3：七个案例，Q4 三相 205→241、Q5/X1 三相 205→281，以及目标身份不匹配负例。只读取指定目标页，冻结起点不能被重写。

红色教学注释不作为业务数据；蓝斜杠排除内接线段，不据此排除整条导体。未知端点/电流保持 null，断路器范围和电压不代替电流。图序不是原 PDF 物理页号；Stage 2 的 pdf_page_number 为 null，Stage 3 的序号仅为合成回归夹具位置。裁剪坐标、来源和待确认项在 `examples_wiring/annotated/provenance.json`。

本地 `profiles/abb/profile.json`、`rules.json` 更新为 1.1.0，保持 experimental，指向独立资源与尚未注册的 `abb_native` 策略，不声明 full_document_extraction。旧远端版本保留，不用 ZH 确定性策略假冒 ABB 提取能力。

## 上传与验证

新增 `prepare_abb_example_images.py` 复现裁剪，`upload_profile_draft.py` 校验并上传 experimental 草稿、逐文件下载核验。命令见 `services/agent/README.md`。

已完成实际上传：

| 字段 | 值 |
| --- | --- |
| Bucket | agent-profile-assets（私有） |
| Profile | abb@1.1.0 |
| 状态 | draft |
| Package ID | e6232c6e-0ec7-5ad0-9bdc-ffcea0f571dd |
| 对象前缀 | abb/1.1.0/3b82b322c020b60862af020c7736c900ded8a20f42c70e7868c45b4f9168783c |
| checksum | sha256:3b82b322c020b60862af020c7736c900ded8a20f42c70e7868c45b4f9168783c |
| 读回核验 | 45 文件全部 checksum 一致 |

`test_abb_resources.py` 与 Registry/Router 回归合计 21 项通过，覆盖 schema、图片路径、完整包、端点字段、Sheet/Cont、Stage 3 起点锁定和负例；新脚本和测试 Ruff 通过，上传脚本 mypy 通过。未调用真实模型，没有重启服务、修改 test0/已有项目绑定或替换 active 包。

## 剩余门槛

expected 是基于图像的转录草稿，仍需工程确认，尤其 X3 起点侧 122/121 的原理号优先级。独立 ABB 确定性策略尚未实现/注册，真实图片字段级模型回归未运行。草稿上传不等于生产发布；确认、策略、回归与审核完成后再启用。
