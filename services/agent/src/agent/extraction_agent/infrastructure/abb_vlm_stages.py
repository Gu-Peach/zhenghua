from __future__ import annotations

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    PageClassificationRequest,
    PageScanRequest,
)
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter


class AbbVlmExtractionStageAdapter(ZhVlmExtractionStageAdapter):
    """ABB-only instructions with the package-bound ABB Prompt and Few-shot."""

    enforce_evidence_contract = False
    zh_endpoint_semantics = False

    def classification_instruction(self, request: PageClassificationRequest) -> str:
        return (
            "读取 ABB 图框功能代码（去掉 =）和 Sheet 当前业务页；Cont 不是当前页。"
            "判断空白/非接线图，不提取连接。输出 PageClassification JSON。"
            f"\nPDF物理页：{request.page.pdf_page_number}\n上下文：{request.known_context or '无'}"
        )

    def scan_instruction(self, request: PageScanRequest) -> str:
        return (
            "扫描 ABB 当前来源页的全部放线连接。小空心圆是放线标记，大空心圆是实际端子；"
            "从小圆圈沿导线找到两侧最近端子，同一段两个小圆圈只输出一条连接。"
            "小圆圈旁相同数字不重复计数，不跨大圆圈或设备合并；蓝斜杠不能代替小圆圈判断。"
            "原理号为标记数字直接拼来源Sheet，无分隔符；无编号用完整端子标识拼Sheet。"
            "例如552和Sheet281生成552281，Q3:2和Sheet205生成Q3:2205。"
            "没有编号的小圆圈仍提取；明确无圈的断路器对外出线同样按实际端子处理。"
            "不使用 ZH 起点白名单。没有当前页终点的跨页线 end=null，并绑定 /Sheet.列行 引用。"
            "Sheet 为业务页，Cont 不是当前页；目标功能未知置空，不从源电位猜目标功能。"
            "signal_name保存导线/箭头旁可见电位名称，如=LV11-Q4 L1，与原理号分开。"
            "current 仅保留直接证据的单一电流，范围、电压或系数不得推算。"
            "批注不作为业务值；没有证据置空并待复核。输出 PageScanData JSON。"
            "可见start/end填写实际端子中心的整图归一化terminal_coordinates及当前PDF物理页，"
            "小圆圈是放线标记，不能把它的坐标当成实际端子坐标。颜色暂不提取。"
            f"\nPDF物理页：{request.page.pdf_page_number}\n当前页上下文：{request.page_context or '无'}"
        )

    def cross_page_instruction(self, request: CrossPageCompletionRequest) -> str:
        return (
            "只处理 ABB 冻结 task 指定的一条跨页连接，以精简来源事实匹配目标图。"
            "用 /Sheet.列行 地址、电位身份和回指交叉核对实际设备端子；地址不是端子。"
            "起点、原理号和来源页不得修改，目标功能可能不同于源电位功能。"
            "遇到第一个实际端子即停止；大圆圈是端子，小圆圈不是端点。"
            "不扫描其他连接，不因目标页小圆圈重复创建连接。无法唯一确认时保留可见字段并待复核。"
            "已有电流不修改，没有直接证据不补电流。输出 CrossPageCompletionData JSON。"
            "end.terminal_coordinates按本次实际输入图归一化及目标PDF物理页填写；"
            "image_view存在时由程序还原整页坐标，不能自行加偏移。"
            "回指可在任意边界且箭头可朝外，按冻结任务归属找终点，不重新定向。"
            "同号N/PE按来源Sheet、电位名称及实际线路区分，不能只按原理号/左右顺序匹配。"
            "裁剪边界外或无法唯一确认时end=null或保留可读字段，并写source_note/uncertainties；禁止空对象。"
            f"\n任务上下文：{request.task_context}\n目标PDF物理页：{request.target_page.pdf_page_number}"
        )
