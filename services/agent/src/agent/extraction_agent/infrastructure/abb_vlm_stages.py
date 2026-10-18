from __future__ import annotations

import json
from typing import Any

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from src.agent.extraction_agent.infrastructure.abb_scan_evidence import (
    AbbScanEvidenceContract,
    AbbScanResponse,
    finalize_abb_scan,
    load_abb_readings,
    raw_abb_scan_example,
)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import (
    ZhVlmExtractionStageAdapter,
    _normalize_page_scan,
)
from src.domain.models.profiles import ProfileBinding


class AbbVlmExtractionStageAdapter(ZhVlmExtractionStageAdapter):
    """ABB-only instructions with the package-bound ABB Prompt and Few-shot."""

    enforce_evidence_contract = False
    zh_endpoint_semantics = False

    def _uses_marker_readings(self, profile: ProfileBinding) -> bool:
        path = profile.resolved_resources.get("scan_evidence_rules")
        if path is None:
            return False
        AbbScanEvidenceContract.model_validate_json(path.read_text(encoding="utf-8"))
        return True

    async def scan_page(self, request: PageScanRequest) -> PageScanData:
        if request.page.blank or request.page.non_wiring or not self._uses_marker_readings(request.profile):
            return await super().scan_page(request)
        response = await self._invoke_stage(
            stage="page_scan",
            request_id=request.run_id,
            profile=request.profile,
            prompt_resource="page_scan_prompt",
            example_resource="wiring_examples",
            example_section="stage2_cases",
            images=[request.page],
            user_text=self.scan_instruction(request),
            output_model=AbbScanResponse,
            normalize=lambda value: _normalize_page_scan(value, request.page.pdf_page_number),
            item_id=f"pdf-page:{request.page.pdf_page_number}",
        )
        return finalize_abb_scan(response, source_sheet=request.page.drawing_page_number)

    def _few_shot_messages(
        self,
        *,
        profile: ProfileBinding,
        resource: str,
        section: str,
        input_json: str | None,
    ) -> list[dict[str, Any]]:
        messages = super()._few_shot_messages(
            profile=profile,
            resource=resource,
            section=section,
            input_json=input_json,
        )
        if section != "stage2_cases" or not self._uses_marker_readings(profile):
            return messages
        folder = profile.resource(resource)
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        cases = manifest.get(section, [])
        assistants = [message for message in messages if message["role"] == "assistant"]
        if len(cases) != len(assistants):
            raise ValueError("ABB scan examples do not match their manifest")
        for case, message in zip(cases, assistants, strict=True):
            evidence = load_abb_readings(folder, case.get("marker_readings", ""))
            message["content"] = json.dumps(
                raw_abb_scan_example(
                    json.loads(message["content"]),
                    evidence,
                ),
                ensure_ascii=False,
            )
        return messages

    def classification_instruction(self, request: PageClassificationRequest) -> str:
        return (
            "读取 ABB 图框功能代码（去掉 =）和 Sheet 当前业务页；Cont 不是当前页。"
            "判断空白/非接线图，不提取连接。输出 PageClassification JSON。"
            f"\nPDF物理页：{request.page.pdf_page_number}\n上下文：{request.known_context or '无'}"
        )

    def scan_instruction(self, request: PageScanRequest) -> str:
        if not self._uses_marker_readings(request.profile):
            return (
                "按当前Profile系统规则读取ABB当前页，输出PageScanData JSON。"
                f"\nPDF物理页：{request.page.pdf_page_number}\n当前页上下文：{request.page_context or '无'}"
            )
        return (
            "按系统规则扫描当前整页所有适用连接，不以示例区域或条数限制范围。"
            "先沿实际导线确定端点及方向，再读本段两侧小圆点数字。"
            "start_marker_number/end_marker_number分别填写原始数字字符串或null；line_number留null由程序生成。"
            "端子从所属元件/排号和实际针脚读取，接收端明确标receiver，未知事实留空。"
            "电流只读本段设备的明确单一值，保留窄范围原文。颜色留空。输出AbbScanResponse JSON。"
            f"\nPDF物理页：{request.page.pdf_page_number}\n当前页上下文：{request.page_context or '无'}"
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        return (
            "只处理 ABB 冻结 task 指定的一条跨页连接，以精简来源事实匹配目标图。"
            "用 /Sheet.列行 地址、电位身份和回指交叉核对实际设备端子；地址不是端子。"
            "起点、原理号和来源页不得修改，目标功能可能不同于源电位功能。"
            "遇到第一个实际端子或明确标注的母线接点即停止；大圆圈是端子，小圆点不是端点。"
            "terminal输出完整身份Q1:2、X1:11，母线L1/N保留原文；标记数字不是端子数字。"
            "不扫描其他连接，不因目标页小圆圈重复创建连接。无法唯一确认时保留可见字段并待复核。"
            "已有电流不修改，没有直接证据不补电流。输出 CrossPageCompletionData JSON。"
            "end.terminal_coordinates按本次实际输入图归一化及目标PDF物理页填写；"
            "image_view存在时由程序还原整页坐标，不能自行加偏移。"
            "回指可在任意边界且箭头可朝外，按冻结任务归属找终点，不重新定向。"
            "同号N/PE按来源Sheet、电位名称及实际线路区分，不能只按原理号/左右顺序匹配。"
            "裁剪边界外或无法唯一确认时end=null或保留可读字段，并写source_note/uncertainties；禁止空对象。"
            f"\n任务上下文：{request.task_context}\n目标PDF物理页：{request.target_page.pdf_page_number}"
        )
