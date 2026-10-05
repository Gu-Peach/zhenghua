from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from ..core.config import Settings
from ..schemas.wire import WireRecord
from .prompt_loader import FewShotExample, load_few_shot_examples


@dataclass(frozen=True)
class ImagePayload:
    name: str
    mime_type: str
    content: bytes
    # Set by the PDF splitter when a page has (almost) no ink; such pages are skipped.
    blank: bool = False
    # Optional embedded PDF text used only for deterministic cross-page grouping hints.
    page_text: str | None = None
    page_number: int | None = None


class VLMError(RuntimeError):
    """Raised when the VLM call succeeds poorly or returns invalid JSON."""


class VLMClient:
    def __init__(
        self,
        settings: Settings,
        prompt: str,
        *,
        few_shot_examples: Sequence[FewShotExample] | None = None,
    ):
        self.settings = settings
        self.prompt = prompt
        self._few_shot_examples = list(few_shot_examples) if few_shot_examples is not None else None

    @property
    def few_shot_examples(self) -> list[FewShotExample]:
        if self._few_shot_examples is None:
            if self.settings.few_shot_images:
                self._few_shot_examples = load_few_shot_examples(self.settings.few_shot_examples_dir)
            else:
                self._few_shot_examples = []
        return self._few_shot_examples

    async def extract_image(self, image: ImagePayload) -> list[WireRecord]:
        return await self.extract_images([image])

    async def extract_images(self, images: Sequence[ImagePayload]) -> list[WireRecord]:
        images = [image for image in images if not image.blank]
        if not images:
            return []

        names = ", ".join(image.name for image in images)
        unit_note = (
            "这几张图属于同一提取单元，端子号和线号可能跨图延续，请合并判断后输出一组记录。"
            if len(images) > 1
            else "当前只有一张图，请只提取该图中可确认的接线记录。"
        )
        content = await self.complete(
            images=images,
            user_text=(
                "请读取以下电气原理图图片。"
                f"{unit_note}"
                "只返回一个 JSON 数组。"
                "起点端子写成端子排名称+端子号（如 XD3:251），终点端子按设备侧原样写（如 X3:3、2-RED），"
                "SPARE 芯端子填 *，PE 芯端子填 PE。"
                f"源文件名：{names}"
            ),
            prefix_messages=build_few_shot_messages(self.few_shot_examples),
        )

        records = parse_vlm_records(content, terminal_strip_mapping=self.settings.terminal_strip_mapping)
        fallback_source = names
        for record in records:
            if not record.source_image or not any(name in record.source_image for name in names.split(", ")):
                record.source_image = fallback_source
        attach_source_metadata(records, images)
        return records

    async def complete(
        self,
        *,
        images: Sequence[ImagePayload],
        user_text: str,
        system_prompt: str | None = None,
        prefix_messages: Sequence[dict[str, Any]] | None = None,
    ) -> str:
        if not images:
            return ""

        payload: dict[str, Any] = {
            "model": self.settings.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt or self.prompt},
                *(prefix_messages or []),
                {"role": "user", "content": _build_user_content(images, user_text)},
            ],
        }
        if self.settings.use_response_format:
            payload["response_format"] = {"type": "json_object"}
        if self.settings.enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": self.settings.enable_thinking}
        if self.settings.max_tokens:
            payload["max_tokens"] = self.settings.max_tokens

        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"

        endpoint = self.settings.chat_completions_url
        timeout = _request_timeout(self.settings.timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(endpoint, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                raise VLMError(
                    "VLM request timed out "
                    f"after {self.settings.timeout_seconds:g}s at {endpoint}. "
                    "Increase VLM_TIMEOUT_SECONDS in .env, or lower VLM_IMAGE_BATCH_SIZE if the provider struggles with multi-image requests."
                ) from exc
            except httpx.RequestError as exc:
                raise VLMError(f"VLM request failed before receiving a response at {endpoint}: {exc}") from exc
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise VLMError(f"VLM request failed: {exc.response.status_code} {exc.response.text}") from exc

        return _extract_message_content(response.json())


def build_few_shot_messages(examples: Sequence[FewShotExample]) -> list[dict[str, Any]]:
    """Turn each example into a user turn (drawings) + assistant turn (expected JSON)."""
    messages: list[dict[str, Any]] = []
    for example in examples:
        notes = "；".join(
            f"{image.name}（{image.role or '图纸'}）：{image.note}" if image.note else image.name
            for image in example.images
        )
        text = (
            f"【示例：{example.title}】请读取以下电气原理图图片，按系统提示的字段只返回 JSON 数组。"
            f"图片说明：{notes}"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for image in example.images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(image.mime_type, image.content), "detail": "high"},
                }
            )
        messages.append({"role": "user", "content": content})
        messages.append({"role": "assistant", "content": example.expected_json})
    return messages


def build_segment_few_shot_messages(examples: Sequence[FewShotExample]) -> list[dict[str, Any]]:
    """Build multimodal Prompt-S examples: two drawing images -> merge JSON."""
    messages: list[dict[str, Any]] = []
    for example in examples:
        notes = "；".join(
            f"{image.name}（{image.role or '图纸'}）：{image.note}" if image.note else image.name
            for image in example.images
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"【分段示例：{example.title}】第一张图是相邻页 A，第二张图是相邻页 B。"
                    "请只依据 Project.NR 和 drawing prefix 判断是否合并。"
                    f"图片说明：{notes}。只输出 Prompt S 要求的 JSON 对象。"
                ),
            }
        ]
        for image in example.images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": _to_data_url(image.mime_type, image.content), "detail": "high"},
                }
            )
        messages.append({"role": "user", "content": content})
        messages.append({"role": "assistant", "content": example.expected_json})
    return messages


def _build_user_content(images: Sequence[ImagePayload], user_text: str) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "text", "text": user_text},
    ]
    for image in images:
        content.append({"type": "image_url", "image_url": {"url": _to_data_url(image.mime_type, image.content), "detail": "high"}})
    return content


def _request_timeout(timeout_seconds: float) -> httpx.Timeout:
    connect_timeout = min(30.0, timeout_seconds)
    write_timeout = min(60.0, timeout_seconds)
    pool_timeout = min(30.0, timeout_seconds)
    return httpx.Timeout(
        timeout_seconds,
        connect=connect_timeout,
        read=timeout_seconds,
        write=write_timeout,
        pool=pool_timeout,
    )


def _to_data_url(mime_type: str, content: bytes) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_message_content(response_json: dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise VLMError("VLM response does not match OpenAI chat completions format.") from exc

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "".join(text_parts)
    raise VLMError("VLM response content is not text.")


def parse_vlm_records(
    content: str,
    *,
    terminal_strip_mapping: Mapping[str, str] | None = None,
) -> list[WireRecord]:
    raw = _strip_code_fence(content).strip()
    parsed = _loads_json(raw)

    if isinstance(parsed, dict):
        for key in ("records", "data", "items", "wires", "result"):
            value = parsed.get(key)
            if isinstance(value, list):
                parsed = value
                break
        else:
            if any(key in parsed for key in ("line_number", "start_terminal", "end_terminal")):
                parsed = [parsed]

    if not isinstance(parsed, list):
        raise VLMError("VLM JSON must be an array of wire records or an object containing a records array.")

    records: list[WireRecord] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise VLMError("Each VLM record must be a JSON object.")
        records.append(_normalize_wire_record(WireRecord.model_validate(item), terminal_strip_mapping))
    return records


def normalize_wire_record(
    record: WireRecord,
    terminal_strip_mapping: Mapping[str, str] | None = None,
) -> WireRecord:
    """Apply deterministic terminal formatting and configured strip mapping."""
    return _normalize_wire_record(record, terminal_strip_mapping)


def attach_source_metadata(records: Sequence[WireRecord], images: Sequence[ImagePayload]) -> list[WireRecord]:
    """Attach deterministic PDF page provenance to VLM records."""
    image_names = [image.name for image in images]
    page_by_name = {
        name: image.page_number or _page_number_from_image_name(name, index + 1)
        for index, (name, image) in enumerate(zip(image_names, images))
    }
    for record in records:
        source_type = (record.source_type or "").strip().lower()
        if source_type not in {"pdf", "external", "mixed", "unknown"}:
            source_type = ""
        mentioned = [name for name in image_names if record.source_image and name in record.source_image]
        if not mentioned and source_type != "external":
            mentioned = image_names
            if not record.source_image:
                record.source_image = ", ".join(image_names) or None
        record.source_pages = (
            sorted({page_by_name[name] for name in mentioned if page_by_name[name] is not None})
            if source_type != "external"
            else []
        )
        if source_type not in {"pdf", "external", "mixed", "unknown"}:
            source_type = "pdf" if record.source_pages else "unknown"
        record.source_type = source_type
        record.external_source_required = source_type in {"external", "mixed"}
        if source_type in {"pdf", "mixed"} and record.source_pages:
            page_note = f"PDF第{','.join(str(page) for page in record.source_pages)}页"
            if not record.source_note:
                record.source_note = page_note
            elif page_note not in record.source_note:
                record.source_note = f"{record.source_note}；{page_note}"
    return list(records)


def _page_number_from_image_name(name: str, fallback: int) -> int | None:
    match = re.search(r"#page=(\d+)", name, flags=re.IGNORECASE) or re.search(r"page[_-](\d+)", name, flags=re.IGNORECASE)
    return int(match.group(1)) if match else fallback


def _normalize_wire_record(
    record: WireRecord,
    terminal_strip_mapping: Mapping[str, str] | None = None,
) -> WireRecord:
    """Normalize terminal formatting without inventing drawing values."""
    line_number = _text(record.line_number)
    if line_number and line_number.upper() == "SPARE":
        record.terminal_strip = None
        record.start_terminal = "*"
        record.end_terminal = "*"
        record.remark = record.remark or "SPARE"
        return record
    if line_number and line_number.upper() == "PE":
        record.terminal_strip = None
        record.start_terminal = "PE"
        record.end_terminal = "PE"
        record.color = record.color or "黄绿"
        record.remark = record.remark or "PE"
        return record

    record.start_terminal = _normalize_terminal(record.start_device, record.start_terminal, force_strip_prefix=True)
    record.end_terminal = _normalize_terminal(record.end_device, record.end_terminal, force_strip_prefix=False)
    record.terminal_strip = (
        _terminal_strip_for_device(record.start_device, terminal_strip_mapping)
        or record.terminal_strip
    )
    return record


def _normalize_terminal(device: Any, terminal: Any, *, force_strip_prefix: bool) -> str | int | None:
    value = _text(terminal)
    if not value:
        return terminal
    if value in {"*", "PE"}:
        return value

    device_text = _text(device)
    device_code = device_text.lstrip("-").upper() if device_text else None
    if _is_terminal_strip_device(device_text):
        suffix = value.rsplit(":", 1)[-1].strip()
        if suffix and not suffix.upper().startswith(("X", "XD")):
            return f"{device_code}:{suffix}"

    normalized = re.sub(r"^-?(XA|XD\d+|XH)\s*[-:]\s*", r"\1:", value, flags=re.IGNORECASE)
    if ":" in normalized and not (force_strip_prefix and _is_terminal_strip_device(device_text)):
        return normalized

    if force_strip_prefix and device_code:
        return f"{device_code}:{value.rsplit(':', 1)[-1].strip()}"
    if _is_terminal_strip_device(device_text):
        return f"{device_code}:{value.rsplit(':', 1)[-1].strip()}"
    return value


def _is_terminal_strip_device(device: str | None) -> bool:
    if not device:
        return False
    code = device.lstrip("-").upper()
    return code == "XA" or code == "XH" or code.startswith("XD")


def _terminal_strip_for_device(device: Any, mapping: Mapping[str, str] | None = None) -> str | None:
    if not _is_terminal_strip_device(_text(device)):
        return None
    code = _text(device).lstrip("-").upper()
    if mapping:
        normalized = {str(key).lstrip("-").upper(): str(value) for key, value in mapping.items()}
        return normalized.get(code)
    if code == "XA" or code in {"XD10", "XD11", "XD12"}:
        return "X1"
    if code in {"XD21", "XD23"}:
        return "X21/X23"
    if code in {"XD22", "XD24"}:
        return "X22/X24"
    if code in {"XD3", "XD5"}:
        return "X3"
    if code == "XD4":
        return "X4"
    if code == "XH":
        return "X5"
    return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _strip_code_fence(content: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return fenced.group(1)
    return content


def _loads_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        candidate = _extract_json_candidate(raw)
        if candidate == raw:
            raise VLMError("VLM did not return valid JSON.")
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise VLMError("VLM did not return valid JSON.") from exc


def _extract_json_candidate(raw: str) -> str:
    array_start = raw.find("[")
    array_end = raw.rfind("]")
    if 0 <= array_start < array_end:
        return raw[array_start : array_end + 1]

    object_start = raw.find("{")
    object_end = raw.rfind("}")
    if 0 <= object_start < object_end:
        return raw[object_start : object_end + 1]
    return raw
