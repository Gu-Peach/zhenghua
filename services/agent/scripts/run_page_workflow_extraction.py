from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = AGENT_ROOT.parents[1]
for path in (AGENT_ROOT, REPOSITORY_ROOT, Path(__file__).resolve().parent):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# isort: split
from run_stage2_groups import load_local_profile, memory_settings  # noqa: E402
from src.agent.extraction_agent.application.page_workflow_extraction import (  # noqa: E402
    run_page_workflow_extraction,
)
from src.config import AgentSettings  # noqa: E402
from src.domain.errors import AgentServiceError  # noqa: E402
from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local PDF with a selected Profile; no database or Storage uploads.",
    )
    parser.add_argument("pdf", type=Path, help="Input PDF path")
    parser.add_argument("--output-dir", type=Path, required=True, help="Test run output directory")
    parser.add_argument("--profile", default="zh", help="Local Profile key; e.g. zh, abb, zh_gantry_reel")
    parser.add_argument("--model", help="Override this run's model ID without editing .env")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--max-pdf-pages", type=int, default=None)
    parser.add_argument("--allow-real-model", action="store_true", help="Explicitly allow paid VLM calls")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if not args.allow_real_model:
        raise SystemExit("Real VLM calls require --allow-real-model; offline smoke tests use pytest.")
    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")
    settings = memory_settings(AgentSettings.from_env())
    if args.model:
        settings = replace(settings, default_model=args.model)
    max_pdf_pages = settings.extraction_max_pdf_pages if args.max_pdf_pages is None else args.max_pdf_pages
    if max_pdf_pages < 0:
        raise SystemExit("--max-pdf-pages must be >= 0; use 0 for all pages")
    if not settings.model_configured:
        raise SystemExit(
            "Model configuration missing. Set AGENT_MODEL_BASE_URL and AGENT_DEFAULT_MODEL "
            "in services/agent/.env (or configure VLM_BASE_URL/VLM_MODEL for compatibility)."
        )
    binding = load_local_profile(settings, args.profile)
    run_id = args.run_id or f"page-workflow-{pdf_path.stem}"
    project_id = args.project_id or pdf_path.stem

    print(
        f"profile={args.profile}, model={settings.default_model}, "
        "memory-only; database_upload=false, storage_upload=false; "
        f"timeout={settings.model_timeout_seconds}s"
    )
    trace_store = LocalModelTraceStore(args.output_dir.resolve() / "model_calls")
    print(f"Model response diagnostics: {trace_store.directory}")
    try:
        result = await run_page_workflow_extraction(
            pdf_path=pdf_path,
            output_dir=args.output_dir,
            profile=binding,
            settings=settings,
            run_id=run_id,
            project_id=project_id,
            max_pdf_pages=max_pdf_pages,
            trace_store=trace_store,
            progress=lambda message: print(f"[agent] {message}"),
        )
    except AgentServiceError as exc:
        print(f"Extraction failed [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    print("\nCompleted")
    print(f"  stage 1 JSON: {result.stage_1_dir}")
    print(f"  stage 2 JSON: {result.stage_2_dir}")
    print(f"  final XLSX:   {result.final_xlsx}")
    template_xlsx = result.stage_2_dir / "wiring-table-import.xlsx"
    if template_xlsx.is_file():
        print(f"  template XLSX:{template_xlsx}")
    if result.execution.extraction_errors:
        print(f"  warnings:     {len(result.execution.extraction_errors)} extraction error(s)")
    if result.execution.validation_warnings:
        print(f"  validation:   {len(result.execution.validation_warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
