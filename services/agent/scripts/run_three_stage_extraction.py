from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = AGENT_ROOT.parents[1]
for path in (AGENT_ROOT / "src", REPOSITORY_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

# isort: split
from agent_service.application.three_stage_extraction import run_three_stage_extraction  # noqa: E402
from agent_service.config import AgentSettings  # noqa: E402
from agent_service.domain.errors import AgentServiceError  # noqa: E402
from agent_service.profiles import ProfileRegistry  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ZH three-stage extraction graph and export JSON/XLSX artifacts.",
    )
    parser.add_argument("pdf", type=Path, help="Input PDF path")
    parser.add_argument("--output-dir", type=Path, required=True, help="Test run output directory")
    parser.add_argument("--profile", default="zh", choices=("zh",), help="Extraction profile")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--max-pdf-pages", type=int, default=None)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    pdf_path = args.pdf.resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")
    settings = AgentSettings.from_env()
    max_pdf_pages = (
        settings.extraction_max_pdf_pages if args.max_pdf_pages is None else args.max_pdf_pages
    )
    if max_pdf_pages < 0:
        raise SystemExit("--max-pdf-pages must be >= 0; use 0 for all pages")
    if not settings.model_configured:
        raise SystemExit(
            "Model configuration missing. Set AGENT_MODEL_BASE_URL and AGENT_DEFAULT_MODEL "
            "in services/agent/.env (or configure VLM_BASE_URL/VLM_MODEL for compatibility)."
        )
    registry = ProfileRegistry(
        profile_root=settings.profile_root,
        workspace_root=settings.workspace_root,
        allow_legacy_references=True,
    )
    registry.load_all()
    binding = registry.bind(args.profile)
    run_id = args.run_id or f"three-stage-{pdf_path.stem}"
    project_id = args.project_id or pdf_path.stem

    print(
        f"profile={args.profile}, model={settings.default_model}, "
        f"endpoint={settings.model_chat_completions_url or settings.model_base_url}, "
        f"timeout={settings.model_timeout_seconds}s"
    )
    try:
        result = await run_three_stage_extraction(
            pdf_path=pdf_path,
            output_dir=args.output_dir,
            profile=binding,
            settings=settings,
            run_id=run_id,
            project_id=project_id,
            max_pdf_pages=max_pdf_pages,
            progress=lambda message: print(f"[agent] {message}"),
        )
    except AgentServiceError as exc:
        print(f"Extraction failed [{exc.code}]: {exc}", file=sys.stderr)
        return 2
    print("\nCompleted")
    print(f"  stage 1 JSON: {result.stage_1_dir}")
    print(f"  stage 2 JSON: {result.stage_2_dir}")
    print(f"  stage 3 JSON: {result.stage_3_dir}")
    print(f"  final XLSX:   {result.final_xlsx}")
    template_xlsx = result.stage_3_dir / "wiring-table-import.xlsx"
    if template_xlsx.is_file():
        print(f"  template XLSX:{template_xlsx}")
    if result.execution.extraction_errors:
        print(f"  warnings:     {len(result.execution.extraction_errors)} extraction error(s)")
    if result.execution.validation_warnings:
        print(f"  validation:   {len(result.execution.validation_warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
