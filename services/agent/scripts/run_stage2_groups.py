"""Test local drawing groups through Stage 2, without any database/Storage client."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

AGENT_ROOT = Path(__file__).resolve().parents[1]
ROOT = AGENT_ROOT.parents[1]
sys.path.insert(0, str(AGENT_ROOT))

# isort: split
from src.agent.extraction_agent.application.document_extraction.settings import Settings  # noqa: E402
from src.agent.extraction_agent.application.extraction_stage_factory import (  # noqa: E402
    build_extraction_stage_dispatcher,
)
from src.agent.extraction_agent.application.page_workflow_extraction import (  # noqa: E402
    ExtractionStageGraphClient,
)
from src.config import AgentSettings  # noqa: E402
from src.domain.models.profiles import ProfileBinding  # noqa: E402
from src.agent.extraction_agent.domain.models.extraction_stages import DrawingPageInput  # noqa: E402
from src.agent.extraction_agent.graphs.document_extraction.state import PageMeta  # noqa: E402
from src.agent.extraction_agent.graphs.document_extraction.workflow import (  # noqa: E402
    run_document_stages_2_3,
)
from src.harness.model_gateway import (  # noqa: E402
    ModelGateway,
    ModelRequest,
    ModelResponse,
    OpenAICompatibleModelGateway,
)
from src.harness.retry import RetryPolicy  # noqa: E402
from src.agent.extraction_agent.infrastructure.document.checkpoint import _write_json_atomic  # noqa: E402
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import _prepare_few_shot_image  # noqa: E402
from src.profiles import ProfileRegistry, ProfileRegistryError  # noqa: E402
from src.agent.extraction_agent.profiles.extraction_policy import default_extraction_policies  # noqa: E402

HEADERS = [
    "页码",
    "原理号",
    "端子排",
    "起点元件",
    "起点描述",
    "起点端子",
    "终点元件",
    "终点描述",
    "终点端子",
    "电流",
    "色标",
    "备注",
    "起点端子坐标",
    "终点端子坐标",
]


def load_pages(
    pages_dir: Path, index_path: Path, groups: list[str]
) -> tuple[list[PageMeta], dict[str, Any], list[int]]:
    """Resolve physical identities from the index, including collision-suffixed images."""
    index = json.loads(index_path.read_text(encoding="utf-8"))
    pages: list[PageMeta] = []
    selected: list[int] = []
    absent_sources: list[str] = []
    for raw in sorted(index["pages"], key=lambda item: int(item["pdf_page"])):
        function, business = raw.get("function"), raw.get("internal_page")
        if not function or business is None:
            continue
        number = int(raw["pdf_page"])
        candidates = [
            pages_dir / function / f"{business}__pdf_{number:04d}.png",
            pages_dir / function / f"{business}.png",
        ]
        image = next((path for path in candidates if path.is_file()), None)
        if image is None:
            if function in groups:
                absent_sources.append(f"{function}/{business} (PDF {number})")
            continue
        pages.append(
            PageMeta(
                page_number=number,
                image_path=str(image.resolve()),
                function=function,
                internal_page=int(business),
                object_loc=raw.get("object_loc"),
                title=raw.get("title"),
                is_non_wiring=bool(raw.get("is_non_wiring")),
                is_stub=bool(raw.get("is_stub")),
                blank=False,
            )
        )
        if function in groups:
            selected.append(number)
    if absent_sources:
        raise ValueError("Missing requested source images: " + ", ".join(absent_sources))
    missing_groups = set(groups) - {page["function"] for page in pages}
    if missing_groups or not selected:
        raise ValueError(f"No indexed images for requested groups: {sorted(missing_groups)}")
    return pages, index, selected


def memory_settings(settings: AgentSettings) -> AgentSettings:
    """Drop database credentials and remote package selection before constructing adapters."""
    return replace(
        settings,
        persistence_backend="memory",
        checkpoint_backend="memory",
        profile_packages_enabled=False,
        supabase_url=None,
        supabase_service_role_key=None,
        profile_root=AGENT_ROOT / "src/agent/extraction_agent/profiles",
        inline_worker=False,
        import_template_path=None,
        extraction_output_mode="library",
    )


class LocalImageClient(ExtractionStageGraphClient):
    def __init__(self, *, pages: list[PageMeta], model_context: dict[str, Any], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._local_pages = {int(page["page_number"]): page for page in pages}
        self._model_context = model_context
        self._completion_mode = False

    @property
    def workflow_fingerprint(self) -> dict[str, Any]:
        return {
            **super().workflow_fingerprint,
            "test_scope": "local-stage2-groups",
            "extract_color": False,
            "model_context": self._model_context,
        }

    def _page(self, image: Any) -> DrawingPageInput:
        page = self._local_pages[int(image.page_number)]
        image_path = Path(page["image_path"])
        if self._completion_mode and int(self._model_context["completion_max_side"]) > 0:
            limit = int(self._model_context["completion_max_side"])
            content, _ = _prepare_few_shot_image(image_path, max_side=limit)
            checksum = hashlib.sha256(content).hexdigest()[:16]
            cached_path = self._output_dir / "model_images" / f"p{image.page_number}-{checksum}.png"
            cached_path.parent.mkdir(parents=True, exist_ok=True)
            if not cached_path.is_file():
                cached_path.write_bytes(content)
            image_path = cached_path
        return DrawingPageInput(
            pdf_page_number=int(page["page_number"]),
            image_path=image_path,
            plant_function=page.get("function"),
            drawing_page_number=page.get("internal_page"),
            object_location=page.get("object_loc"),
            blank=bool(page.get("blank")),
            non_wiring=bool(page.get("is_non_wiring")),
        )

    async def scan_page(self, image: Any, *, page_context: str = "") -> Any:
        result = await super().scan_page(
            image,
            page_context=(
                "本次测试不提取色标：每条 connection.color 必须为 null。其他字段按图中证据读取。\n"
                + page_context
            ),
        )
        for unit in result.units:
            for connection in unit.connections:
                connection.color = None
        return result

    async def resolve_cross_page(
        self, target_image: Any, *, source_image: Any | None = None, task_context: str = ""
    ) -> Any:
        self._completion_mode = bool(source_image)
        try:
            return await super().resolve_cross_page(
                target_image, source_image=source_image, task_context=task_context
            )
        finally:
            self._completion_mode = False


class RecordingGateway:
    """Record safe model outputs/usage locally, never messages, keys, or image URLs."""

    def __init__(self, gateway: ModelGateway, directory: Path, *, model: str) -> None:
        self.gateway, self.directory = gateway, directory
        self.model = model
        self.invocation_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.calls: list[dict[str, Any]] = []

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        started = perf_counter()
        result = None
        error = None
        diagnostic: dict[str, Any] = {}
        cache_hit = False
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "model": request.model or self.model,
                    "messages": request.messages,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "json_mode": request.json_mode,
                    "thinking": request.enable_thinking,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cache_path = self.directory / "model_cache" / f"{fingerprint}.json"
        try:

            def load_cache() -> dict[str, Any] | None:
                if request.output_model is not None or not cache_path.is_file():
                    return None
                try:
                    return json.loads(cache_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None

            saved = await asyncio.to_thread(load_cache)
            if saved is not None:
                result = ModelResponse(
                    content=saved["content"],
                    model=saved["model"],
                    parsed=None,
                    duration_seconds=0,
                    attempts=0,
                    usage={},
                )
                cache_hit = True
            else:
                result = await self.gateway.invoke(request)
                if request.output_model is None:
                    await asyncio.to_thread(
                        _write_json_atomic,
                        cache_path,
                        {
                            "content": result.content,
                            "model": result.model,
                            "usage": result.usage,
                        },
                    )
            return result
        except Exception as exc:
            error = type(exc).__name__
            details = getattr(exc, "details", {})
            diagnostic = {
                key: details[key]
                for key in (
                    "status_code",
                    "provider_message",
                    "provider_code",
                    "provider_type",
                    "provider_param",
                )
                if key in details
            }
            raise
        finally:
            entry = {
                "call": len(self.calls) + 1,
                "model": result.model if result else self.model,
                "stage": request.metadata.get("stage"),
                "item_id": request.metadata.get("item_id"),
                "duration_seconds": round(perf_counter() - started, 3),
                "error_type": error,
                "error_details": diagnostic,
                "cache_hit": cache_hit,
                "usage": result.usage if result else {},
                "attempts": result.attempts if result else None,
                "response_content": result.content if result else None,
            }
            self.calls.append(entry)
            await asyncio.to_thread(
                _write_json_atomic,
                self.directory / "model_calls" / self.invocation_id / f"{len(self.calls):04d}.json",
                entry,
            )


def table_rows(records: list[dict[str, Any]]) -> list[list[Any]]:
    rows = []
    for record in records:
        function, number = record.get("drawing_function"), record.get("drawing_page_number")
        page = (
            f"{str(function).replace('.', '')}{int(number):02d}" if function and number is not None else None
        )
        rows.append(
            [
                page,
                record.get("line_number"),
                record.get("terminal_strip"),
                record.get("start_device") or record.get("start_location"),
                record.get("start_name"),
                record.get("start_terminal"),
                record.get("end_device") or record.get("end_location"),
                record.get("end_name"),
                record.get("end_terminal"),
                record.get("current"),
                None,
                record.get("remark"),
                json.dumps(record["start_terminal_coordinates"], ensure_ascii=False)
                if record.get("start_terminal_coordinates") is not None else None,
                json.dumps(record["end_terminal_coordinates"], ensure_ascii=False)
                if record.get("end_terminal_coordinates") is not None else None,
            ]
        )
    return rows


def model_statistics(output: Path) -> dict[str, Any]:
    """Aggregate recorded attempts across resumptions; cached responses incur no new usage."""
    calls = [
        json.loads(path.read_text(encoding="utf-8")) for path in (output / "model_calls").rglob("*.json")
    ]
    real = [call for call in calls if not call.get("cache_hit")]
    totals = {
        field: sum(int(call.get("usage", {}).get(field) or 0) for call in real)
        for field in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    return {
        "recorded_model_calls_total": len(real),
        "recorded_failed_calls_total": sum(bool(call.get("error_type")) for call in real),
        "recorded_model_seconds_total": round(
            sum(float(call.get("duration_seconds") or 0) for call in real), 3
        ),
        "usage_totals": totals,
        "duration_basis": "duration_seconds describes the latest extraction invocation",
    }


def template_style(path: Path) -> dict[str, Any]:
    """Read only layout metadata and headers; reference answer rows never enter the VLM."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(path) as archive:
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        styles = ET.fromstring(archive.read("xl/styles.xml"))
        strings = (
            ET.fromstring(archive.read("xl/sharedStrings.xml"))
            if "xl/sharedStrings.xml" in archive.namelist()
            else None
        )
        shared = ["".join(item.itertext()) for item in strings] if strings is not None else []
        cells = sheet.findall("m:sheetData/m:row", ns)[0].findall("m:c", ns)
        headers = [
            shared[int(cell.find("m:v", ns).text)]
            if cell.get("t") == "s"
            else "".join(cell.find("m:is", ns).itertext())
            for cell in cells
        ]
        if headers != HEADERS[:12]:
            raise ValueError("Template header order differs from the required 12-column layout.")
        fmt = sheet.find("m:sheetFormatPr", ns)
        widths = [float(fmt.get("defaultColWidth", "8.89"))] * 12
        for col in sheet.findall("m:cols/m:col", ns):
            for i in range(int(col.get("min")) - 1, min(12, int(col.get("max")))):
                widths[i] = float(col.get("width", "8.89"))
        style = styles.find("m:cellXfs", ns)[int(cells[0].get("s", "0"))]
        font = styles.find("m:fonts", ns)[int(style.get("fontId", "0"))]
        name, size = font.find("m:name", ns), font.find("m:sz", ns)
        return {
            "font": name.get("val") if name is not None else "宋体",
            "size": float(size.get("val")) if size is not None else 9,
            "widths": [*widths, 42, 42],
            "body_height": 21.6,
            "header_fill": "#C0C0C0",
        }


def export_xlsx(output: Path, template: Path, *, node: Path, modules: Path) -> Path:
    """Run the local Artifact Tool builder against records.json, with no network client."""
    runtime = output / "_xlsx_runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    junction = runtime / "node_modules"
    if not junction.exists():
        if os.name == "nt":
            # Native creation only; literal PowerShell strings prevent path interpolation.
            quoted_junction = str(junction).replace("'", "''")
            quoted_modules = str(modules).replace("'", "''")
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"New-Item -ItemType Junction -Path '{quoted_junction}' "
                    f"-Target '{quoted_modules}' | Out-Null",
                ],
                check=True,
                capture_output=True,
            )
        else:
            junction.symlink_to(modules, target_is_directory=True)
    if junction.resolve() != modules.resolve():
        raise ValueError("Unexpected exporter dependency junction target.")
    builder = runtime / "export_stage2_xlsx.mjs"
    shutil.copyfile(Path(__file__).with_name("export_stage2_xlsx.mjs"), builder)
    subprocess.run(
        [str(node), str(builder), str(output / "table.json"), str(output / "result.xlsx"), str(template)],
        check=True,
    )
    return output / "result.xlsx"


def load_local_profile(settings: AgentSettings, profile_key: str) -> ProfileBinding:
    """Bind an explicitly chosen local profile, independently of other invalid templates."""
    registry = ProfileRegistry(
        profile_root=settings.profile_root, workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all(strict=False)
    try:
        profile = registry.bind(profile_key, allow_experimental=True)
    except ProfileRegistryError as exc:
        raise ProfileRegistryError(
            exc.message, details={"errors": list(registry.errors)}
        ) from exc
    for error in registry.errors:
        print(f"跳过无效的其他Profile（本次使用{profile_key}）：{error}", file=sys.stderr, flush=True)
    return profile


def load_local_zh_profile(settings: AgentSettings) -> ProfileBinding:
    """Retain the existing ZH-only helper for callers using the old interface."""
    return load_local_profile(settings, "zh")


def failure_report(exc: Exception) -> dict[str, Any]:
    """Expose registry resource errors while keeping other exception text private."""
    report: dict[str, Any] = {
        "status": "FAILED",
        "error_type": type(exc).__name__,
        "error_code": getattr(exc, "code", None),
        "database_upload": False,
        "storage_upload": False,
    }
    if isinstance(exc, ProfileRegistryError):
        report["message"] = exc.message
        report["profile_errors"] = list(exc.details.get("errors", []))
    return report


async def execute(args: argparse.Namespace, *, stages: Any | None = None) -> dict[str, Any]:
    output = args.output_dir.resolve()
    if (output / "result.xlsx").resolve() == args.template.resolve():
        raise ValueError("The output workbook must not overwrite the reference template.")
    output.mkdir(parents=True, exist_ok=True)
    pages, index, selected = await asyncio.to_thread(
        load_pages, args.pages_dir.resolve(), args.index.resolve(), args.groups
    )
    if args.max_source_pages:
        selected = selected[: args.max_source_pages]
    style = await asyncio.to_thread(template_style, args.template.resolve())
    catalog = {int(page["page_number"]): page for page in pages}
    manifest = {
        "groups": args.groups,
        "selected_pages": [catalog[number] for number in selected],
        "available_target_pages": len(pages),
        "database_upload": False,
        "storage_upload": False,
        "extract_color": False,
        "headers": HEADERS,
        "template": str(args.template.resolve()),
    }
    if not args.export_only:
        _write_json_atomic(output / "input_manifest.json", manifest)
    if not args.allow_real_model and stages is None and not args.export_only:
        print(f"预检完成：{len(selected)} 来源页，{len(pages)} 张本地可用图片；未调用模型。", flush=True)
        return {"status": "PREFLIGHT", "source_pages": len(selected)}
    gateway = None
    started = perf_counter()
    if args.export_only:
        records = json.loads((output / "records.json").read_text(encoding="utf-8"))
        summary = json.loads((output / "run-result.json").read_text(encoding="utf-8"))
    else:
        settings = memory_settings(AgentSettings.from_env())
        if getattr(args, "model", None):
            settings = replace(settings, default_model=args.model)
        profile = load_local_profile(settings, getattr(args, "profile", "zh"))
        if stages is None:
            if not settings.model_configured:
                raise ValueError("Configure the model in services/agent/.env before a real test.")
            gateway = RecordingGateway(
                OpenAICompatibleModelGateway(
                    base_url=settings.model_base_url or settings.model_chat_completions_url or "",
                    chat_completions_url=settings.model_chat_completions_url,
                    api_key=settings.model_api_key,
                    default_model=settings.default_model or "",
                    timeout_seconds=settings.model_timeout_seconds,
                    retry_policy=RetryPolicy(max_retries=settings.model_max_retries),
                ),
                output,
                model=settings.default_model or "unconfigured",
            )
            stages = build_extraction_stage_dispatcher(settings, gateway=gateway)
        client = LocalImageClient(
            pages=pages,
            model_context={
                "model": settings.default_model,
                "max_tokens": settings.model_max_tokens,
                "thinking": settings.model_enable_thinking,
                "fewshot_side": settings.model_fewshot_max_image_side,
                "completion_max_side": getattr(args, "completion_max_side", 3000),
            },
            run_id=args.run_id,
            project_id="local-stage2-test",
            profile=profile,
            stages=stages,
            output_dir=output,
            durable=None,
        )
        print(
            f"Stage 2：{len(selected)} 来源页，Profile {profile.profile.key}@{profile.profile.version}，"
            f"model={settings.default_model}; memory-only",
            flush=True,
        )
        result = await run_document_stages_2_3(
            pages=pages,
            source_page_numbers=selected,
            drawing_index=index,
            output_path=output,
            settings=Settings.from_agent(settings),
            extraction_client=client,
            policy=default_extraction_policies().resolve(profile.adapter),
            progress=lambda text: print(text, flush=True),
            assemble_output=False,
        )
        records = result.state.get("connection_records", [])
        for record in records:
            record["color"] = None
        _write_json_atomic(output / "records.json", records)
        _write_json_atomic(output / "page-scan-results.json", result.state.get("page_scan_results", {}))
        _write_json_atomic(output / "cross-page-results.json", result.state.get("cross_page_results", {}))
        _write_json_atomic(output / "cross-page-tasks.json", result.state.get("cross_page_tasks", []))
        summary = {
            "status": "COMPLETED",
            "run_id": args.run_id,
            "model": settings.default_model,
            "profile": profile.profile.model_dump(mode="json"),
            "groups": args.groups,
            "source_pages": len(selected),
            "records": len(records),
            "needs_review": sum(record.get("status") == "needs_review" for record in records),
            "duration_seconds": round(perf_counter() - started, 3),
            "model_calls": sum(not entry.get("cache_hit") for entry in gateway.calls) if gateway else 0,
            "model_cache_hits": sum(bool(entry.get("cache_hit")) for entry in gateway.calls)
            if gateway
            else 0,
            "usage": [entry["usage"] for entry in gateway.calls] if gateway else [],
            "cost_usd": None,
            "cost_note": "Provider pricing/cost not supplied; no cost estimate fabricated.",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
            "database_upload": False,
            "storage_upload": False,
            "extract_color": False,
            "warnings": result.validation_warnings,
            "errors": result.extraction_errors,
        }
        _write_json_atomic(output / "run-result.json", summary)
    _write_json_atomic(
        output / "table.json", {"headers": HEADERS, "rows": table_rows(records), "style": style}
    )
    summary.update(model_statistics(output))
    summary["records_by_group"] = dict(Counter(record.get("drawing_function") for record in records))
    _write_json_atomic(output / "run-result.json", summary)
    previous_failure = output / "failure.json"
    if previous_failure.is_file():
        failures = output / "failures"
        failures.mkdir(exist_ok=True)
        previous_failure.rename(failures / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json")
    if not args.skip_xlsx:
        await asyncio.to_thread(
            export_xlsx, output, args.template.resolve(), node=args.node, modules=args.node_modules
        )
    print(f"完成：{len(records)} 条连接；输出目录 {output}", flush=True)
    return summary


def parse_args() -> argparse.Namespace:
    dependency = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node"
    parser = argparse.ArgumentParser(description="Local Stage 2 test; no database or Storage uploads.")
    parser.add_argument("--pages-dir", type=Path, default=ROOT / "docs/test/pages")
    parser.add_argument(
        "--index", type=Path, default=ROOT / "docs/test/pages/agent/drawing_index.json"
    )
    parser.add_argument("--template", type=Path, default=ROOT / "docs/test/1641.xlsx")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/test/run_stage2")
    parser.add_argument("--groups", nargs="+", default=["002.C", "002.M"])
    parser.add_argument("--profile", default="zh", help="Local Profile key; e.g. zh, abb, zh_gantry_reel")
    parser.add_argument("--run-id", default="local-stage2-002c-002m")
    parser.add_argument("--max-source-pages", type=int, default=0)
    parser.add_argument("--allow-real-model", action="store_true")
    parser.add_argument("--model", help="Override the model ID for this run; does not edit .env")
    parser.add_argument(
        "--completion-max-side",
        type=int,
        default=3000,
        help="Limit the two completion query images; leave original page files unchanged",
    )
    parser.add_argument(
        "--export-only", action="store_true", help="Export existing records without model calls"
    )
    parser.add_argument("--skip-xlsx", action="store_true", help="Only for offline mocked tests")
    parser.add_argument("--node", type=Path, default=dependency / "bin/node.exe")
    parser.add_argument("--node-modules", type=Path, default=dependency / "node_modules")
    args = parser.parse_args()
    if args.max_source_pages < 0:
        parser.error("--max-source-pages must be >= 0")
    if args.completion_max_side < 0:
        parser.error("--completion-max-side must be >= 0 (0 keeps original images)")
    return args


if __name__ == "__main__":
    arguments = parse_args()
    try:
        asyncio.run(execute(arguments))
    except Exception as exc:
        report = failure_report(exc)
        _write_json_atomic(
            arguments.output_dir / "failure.json",
            report,
        )
        if report.get("message"):
            print(f"Profile加载失败：{report['message']}", file=sys.stderr)
        for error in report.get("profile_errors", []):
            print(f"  {error}", file=sys.stderr)
        print(f"测试失败：{type(exc).__name__}；已完成页仍保留，可在同目录恢复。", file=sys.stderr)
        raise SystemExit(2) from None
