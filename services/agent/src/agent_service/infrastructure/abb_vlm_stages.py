from __future__ import annotations

from ..domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
    PageClassificationRequest,
    PageScanRequest,
)
from .zh_vlm_stages import ZhVlmExtractionStageAdapter


class AbbVlmExtractionStageAdapter(ZhVlmExtractionStageAdapter):
    """ABB-only instructions with the package-bound ABB Prompt and Few-shot."""

    enforce_evidence_contract = False

    def completion_images(self, request: CrossPageCompletionRequest) -> list[DrawingPageInput]:
        # Preserve ABB's existing single-target-page query contract in this ZH change.
        return [request.target_page]

    def classification_instruction(self, request: PageClassificationRequest) -> str:
        return (
            "读取 ABB 图框功能代码（去掉 =）和 Sheet 当前业务页；Cont 不是当前页。"
            "判断空白/非接线图，不提取连接。输出 PageClassification JSON。"
            f"\nPDF物理页：{request.page.pdf_page_number}\n上下文：{request.known_context or '无'}"
        )

    def scan_instruction(self, request: PageScanRequest) -> str:
        return (
            "扫描 ABB 当前来源页的全部外接放线连接，按实际端子排分组。空心圆是外接线标志；"
            "斜杠内部接线段排除，用户明确指定的断路器外出线按本 Profile 规则处理。"
            "不使用 ZH 起点白名单。没有当前页终点的跨页线 end=null，并绑定 /Sheet.列行 引用。"
            "Sheet 为业务页，Cont 不是当前页；目标功能未知置空，不从源电位猜目标功能。"
            "current 仅保留直接证据的单一电流，范围、电压或系数不得推算。"
            "批注不作为业务值；没有证据置空并待复核。输出 PageScanData JSON。"
            f"\nPDF物理页：{request.page.pdf_page_number}\n当前页上下文：{request.page_context or '无'}"
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        return (
            "只处理 ABB 冻结 task 指定的一条跨页连接，图片是唯一目标页。"
            "用 /Sheet.列行 地址、电位身份和回指交叉核对实际设备端子；地址不是端子。"
            "起点、原理号和来源页不得修改，目标功能可能不同于源电位功能。"
            "不扫描其他连接，不能沿斜杠内部接线生成外接线。无法唯一确认时 end=null 并待复核。"
            "已有电流不修改，没有直接证据不补电流。输出 CrossPageCompletionData JSON。"
            f"\n任务上下文：{request.task_context}\n目标PDF物理页：{request.target_page.pdf_page_number}"
        )
