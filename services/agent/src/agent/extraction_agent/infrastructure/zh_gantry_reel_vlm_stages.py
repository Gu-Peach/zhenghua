from __future__ import annotations

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    PageClassificationRequest,
    PageScanRequest,
)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter


class ZhGantryReelVlmAdapter(ZhVlmExtractionStageAdapter):
    """Reuse structured multimodal transport, with independent grid-template instructions."""

    enforce_evidence_contract = True
    zh_endpoint_semantics = False

    def classification_instruction(self, request: PageClassificationRequest) -> str:
        return (
            "读取图框 SH.NO.，不要把 CONT.ON.SH 或 PDF物理页码当作当前业务页。"
            "本模板没有 Plant Function/Page Number；按系统 Prompt 的可逆规则映射接口字段。"
            "reason 保留原始 SH.NO.。"
            "封面/端子图表为 non_wiring，不创建连接。只输出 PageClassificationData JSON。"
            f"\nPDF物理页={request.page.pdf_page_number}; context={request.known_context}"
        )

    def scan_instruction(self, request: PageScanRequest) -> str:
        return (
            "先定位放线斜杠，沿两侧找到最近实际端子或跨页箭头，遇端子停止。"
            "只用同一放线段的箭头判断来源/接收；无箭头按实际接线判断，不按端子类型定向。"
            "同排数字端子继承实际X排号；只读取本图可见元件、端子和原理号，未知字段为空。"
            "端子图表/封面不重复提取；不从人工表补外部端子、业务别名或电缆编号。"
            "terminal_board保存实际排号/接口，terminal_strip留null由程序处理，颜色留null。"
            "跨页引用例如 1B30B 必须绑定连接，目标按 SH.NO. 映射，end=null。"
            "只输出 PageScanData JSON，source_drawing_pages 保留原始页标。"
            "每个可见端点填写terminal_coordinates：实际端子中心的整图归一化x/y及当前PDF物理页，无法定位则null。"
            f"\nPDF物理页={request.page.pdf_page_number}; context={request.page_context}"
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        return (
            "这是 Stage 2 内部双图补全，只处理冻结连接，不改起点、不扫描目标页其他线路。"
            "按原始 SH.NO. + 数字列 + 字母行、原理号/回指和实际路径匹配目标入页线路。"
            "从对应入页箭头沿线读取第一个实际端子，遇端子停止，不追到下游设备。"
            "正常回指是匹配证据。电位/信号名不能冒充针脚；设备或端子未标注则该字段 null 并通过uncertainties报告依据。"
            "终点以图中标注为准，terminal_strip留null由程序处理，不从人工表猜终点。"
            "只输出 CrossPageCompletionData JSON。"
            "end.terminal_coordinates读取目标实际端子中心的整图归一化x/y和目标PDF物理页，不改来源坐标。"
            f"\nsource_pdf={request.source_page.pdf_page_number if request.source_page else 'unknown'}"
            f"; target_pdf={request.target_page.pdf_page_number}; task={request.task_context}"
        )
