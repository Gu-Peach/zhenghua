from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from time import perf_counter

from .agents.wiring_graph import run_wiring_agent
from .core.config import ConfigError, load_settings
from .services.excel_writer import records_to_xlsx_bytes
from .services.file_inputs import InputFileError, path_to_image_payloads
from .services.prompt_loader import load_prompt
from .services.test_case_runner import results_to_json, run_test_cases
from .services.vlm_client import ImagePayload, VLMClient, VLMError


async def _run(args: argparse.Namespace) -> None:
    settings = load_settings(model=args.model, base_url=args.base_url, api_key=args.api_key, max_pdf_pages=args.max_pdf_pages)
    prompt = load_prompt(settings.prompt_path)
    _progress(
        f"Using model={settings.model}, endpoint={settings.chat_completions_url}, "
        f"timeout={settings.timeout_seconds:g}s, image_batch_size={settings.image_batch_size}"
    )

    if args.test_case_dir:
        results = await run_test_cases(
            case_root=_resolve_test_case_dir(args.test_case_dir),
            settings=settings,
            prompt=prompt,
            output_name=args.case_output_name,
            sheet_title=args.sheet_title,
            progress=_progress,
        )
        print(results_to_json(results))
        if any(result.status != "success" for result in results):
            raise SystemExit(1)
        return

    if args.agent_pdf:
        pdf_path = Path(args.agent_pdf)
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)
        segment_prompt_path = settings.segment_prompt_path or settings.grouping_prompt_path
        if segment_prompt_path is None:
            raise ConfigError("Missing VLM segment prompt path.")
        segment_prompt = load_prompt(segment_prompt_path)
        _progress(
            f"Running LangGraph agent for {pdf_path}; segment_concurrency={settings.segment_concurrency}, "
            f"render_dpi={settings.pdf_render_dpi}"
        )
        result = await run_wiring_agent(
            pdf_path=pdf_path,
            output_path=Path(args.output),
            settings=settings,
            extraction_prompt=prompt,
            segment_prompt=segment_prompt,
            progress=_progress,
            output_mode=args.agent_output_mode,
        )
        state = result.state
        record_count = sum(len(records) for records in state["wiring_records"].values())
        print(
            f"LangGraph completed: {len(state['pages'])} page(s), "
            f"{len(state['segments'])} segment(s), {record_count} record(s); output={args.output}"
        )
        if result.extraction_errors:
            raise SystemExit(1)
        return

    if not args.sources:
        raise SystemExit("Please provide drawing sources or use --test-case-dir.")

    images: list[ImagePayload] = []
    for source in args.sources:
        images.extend(path_to_image_payloads(Path(source), settings.max_pdf_pages))
    blank_count = sum(1 for image in images if image.blank)
    images = [image for image in images if not image.blank]
    suffix = f", skipped {blank_count} blank page(s)" if blank_count else ""
    _progress(f"Prepared {len(images)} image payload(s) from {len(args.sources)} source file(s){suffix}")
    if not images:
        raise SystemExit("No non-blank drawing pages were found.")

    client = VLMClient(settings, prompt)
    records = []
    batches = [images[index : index + settings.image_batch_size] for index in range(0, len(images), settings.image_batch_size)]
    for batch_index, batch in enumerate(batches, start=1):
        started_at = perf_counter()
        names = ", ".join(image.name for image in batch)
        _progress(f"Calling VLM batch {batch_index}/{len(batches)} ({len(batch)} image(s)); files: {names}")
        records.extend(await client.extract_images(batch))
        _progress(f"Batch {batch_index}/{len(batches)} returned in {_format_seconds(perf_counter() - started_at)}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(records_to_xlsx_bytes(records, sheet_title=args.sheet_title))
    print(f"Wrote {len(records)} records to {output_path}")


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _format_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60)
    return f"{int(minutes)}m {remainder:.0f}s"


def _resolve_test_case_dir(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute() or path.exists():
        return path

    backend_dir = Path(__file__).resolve().parents[1]
    project_dir = backend_dir.parent
    candidates = [backend_dir / path, project_dir / path]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract wiring records from electrical drawings with an OpenAI-compatible VLM.")
    parser.add_argument("sources", nargs="*", help="Image or PDF paths")
    parser.add_argument("-o", "--output", default="outputs/wiring-table.xlsx", help="Output xlsx path")
    parser.add_argument("--sheet-title", default="放线表", help="Workbook sheet title")
    parser.add_argument("--model", default=None, help="Override VLM_MODEL")
    parser.add_argument("--base-url", default=None, help="Override VLM_BASE_URL or OPENAI_BASE_URL")
    parser.add_argument("--api-key", default=None, help="Override VLM_API_KEY or OPENAI_API_KEY")
    parser.add_argument("--max-pdf-pages", type=int, default=None, help="Maximum pages rendered per PDF")
    parser.add_argument(
        "--agent-pdf",
        default=None,
        help="Run the LangGraph V1 pipeline for one PDF. Use -o for the xlsx or library output path.",
    )
    parser.add_argument(
        "--agent-output-mode",
        choices=("library", "single_xlsx"),
        default=None,
        help="Override VLM_OUTPUT_MODE for --agent-pdf.",
    )
    parser.add_argument(
        "--test-case-dir",
        nargs="?",
        const="test_case",
        default=None,
        help="Run all case folders under this directory and write outputs into each folder. Defaults to backend/test_case when no value is provided.",
    )
    parser.add_argument("--case-output-name", default="result", help="Output basename used by --test-case-dir")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except (ConfigError, FileNotFoundError, InputFileError, VLMError, RuntimeError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
