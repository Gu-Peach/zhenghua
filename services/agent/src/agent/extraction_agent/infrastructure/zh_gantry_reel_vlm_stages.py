from __future__ import annotations

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    PageClassificationRequest,
    PageScanRequest,
)
from src.agent.extraction_agent.infrastructure.document.completion_context import TargetOnlyCompletionContext
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from src.agent.extraction_agent.profiles.zh_gantry_reel.policy import decode_sheet


class ZhGantryReelVlmAdapter(ZhVlmExtractionStageAdapter):
    """Reuse structured multimodal transport, with independent grid-template instructions."""

    enforce_evidence_contract = True
    zh_endpoint_semantics = False

    def completion_context(self, request: CrossPageCompletionRequest) -> TargetOnlyCompletionContext:
        context = super().completion_context(request)
        updates = {}
        for key in ("source_page", "target_page"):
            page = getattr(context, key)
            if page.drawing_function and page.drawing_page_number:
                try:
                    label = decode_sheet(page.drawing_function, page.drawing_page_number)
                except ValueError:
                    continue
                updates[key] = page.model_copy(update={"drawing_label": label})
        return context.model_copy(update=updates)

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
            "signal_name保存箭头旁信号/电位名，例如PN2，与图上原理号分开。"
            "只输出 PageScanData JSON，source_drawing_pages 保留原始页标。"
            "每个可见端点填写terminal_coordinates：实际端子中心的整图归一化x/y及当前PDF物理页，无法定位则null。"
            f"\nPDF物理页={request.page.pdf_page_number}; context={request.page_context}"
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        return (
            "这是 Stage 2 内部目标图补全，从初扫来源事实匹配目标图；不改起点、不扫描其他线路。"
            "source_page/target_page.drawing_label为原生SH.NO.，GCR索引只查页，不替代原生页标。"
            "按原始 SH.NO. + 数字列 + 字母行、原理号/回指和实际路径匹配目标入页线路。"
            "从匹配回指沿线读取第一个实际端子，遇端子停止，不追到下游设备。"
            "回指可在任意边界且箭头可朝外，按冻结任务归属补终点，不重新定向。"
            "重复原理号、N/PE须结合来源SH.NO.、signal_name和完整引用区分，不按左右顺序配对。"
            "正常回指是匹配证据，电位/信号名不能冒充针脚；"
            "设备或端子未标注则该字段null，并通过uncertainties报告依据。"
            "终点以图中标注为准，terminal_strip留null由程序处理，不从人工表猜终点。"
            "只输出 CrossPageCompletionData JSON。"
            "end.terminal_coordinates按实际输入图归一化x/y及目标PDF物理页读取；"
            "image_view存在时由程序回映整页，不自行加偏移。"
            "若匹配线离开裁剪边界或针脚不可辨，保留可见字段并写source_note/uncertainties；禁止返回空对象。"
            f"\nsource_pdf={request.source_page.pdf_page_number if request.source_page else 'unknown'}"
            f"; target_pdf={request.target_page.pdf_page_number}; task={request.task_context}"
        )
