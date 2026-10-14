from __future__ import annotations

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    PageClassificationRequest,
    PageScanRequest,
)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter


class ZhGantryReelVlmAdapter(ZhVlmExtractionStageAdapter):
    """Reuse structured multimodal transport, with independent grid-template instructions."""

    enforce_evidence_contract = False

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
            "按本图放线斜杠、端子与实际导线识别来源连接；无 XA/XD 白名单。"
            "箭头只判断相对端子的来源/接收，未能判断保留证据与复核。"
            "电位名和引用坐标不是端子号；相同原理号的不同芯/分支分别保留。"
            "端子图表/封面不重复提取；XLSX 外部柜端子、MVCR业务名、颜色/备用芯/型号/线号不能补造。"
            "以实际 X0/X1/X21/X22/X3 为 terminal_board/strip，不用电缆类别反改端子。"
            "跨页引用例如 1B30B 必须绑定连接，目标按 SH.NO. 映射，end=null。"
            "只输出 PageScanData JSON，source_drawing_pages 保留原始页标。"
            f"\nPDF物理页={request.page.pdf_page_number}; context={request.page_context}"
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        return (
            "这是 Stage 2 内部双图补全，只处理冻结连接，不改起点、不扫描目标页其他线路。"
            "按原始 SH.NO. + 数字列 + 字母行、信号/原理号/回指和实际路径共同匹配。"
            "正常回指是匹配证据。电位/信号名不能冒充针脚；设备或端子未标注则该字段 null 并 needs_review。"
            "禁止使用未提供的外部柜图、XLSX 标准答案或业务映射猜终点。只输出 CrossPageCompletionData JSON。"
            f"\nsource_pdf={request.source_page.pdf_page_number if request.source_page else 'unknown'}"
            f"; target_pdf={request.target_page.pdf_page_number}; task={request.task_context}"
        )
