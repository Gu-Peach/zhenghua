from __future__ import annotations

"""Upload one PDF to the running backend and collect the three Agent stages.

Example:
    python scripts/test_backend_pipeline.py backend/cases/test.pdf \
        --output-dir backend/cases/test/run-003
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import httpx


STAGE_FILES = {
    "01_page_classification": (
        "page-classifications.json",
        "plant-function-groups.json",
        "drawing_index.json",
    ),
    "02_page_scan": (
        "page-scan-checkpoint.json",
        "page-scan-results.json",
        "wire-units-checkpoint.json",
        "wire-units.json",
        "connection-records.json",
        "stage2-table.json",
    ),
    "03_cross_page_completion": (
        "cross-page-tasks.json",
        "cross-page-checkpoint.json",
        "cross-page-results.json",
        "table.json",
    ),
}

RUN_FILES = (
    "progress.jsonl",
    "errors.json",
    "validation-warnings.json",
)


def main() -> int:
    args = _parse_args()
    pdf_path = args.pdf.resolve() if args.pdf is not None else None
    if not args.resume_job_id:
        if pdf_path is None:
            raise SystemExit("Provide a PDF path or --resume-job-id.")
        if not pdf_path.is_file():
            raise SystemExit(f"PDF not found: {pdf_path}")
        if pdf_path.suffix.lower() != ".pdf":
            raise SystemExit(f"Input must be a PDF: {pdf_path}")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    base_url = args.base_url.rstrip("/") + "/"
    timeout = httpx.Timeout(args.request_timeout, connect=min(30.0, args.request_timeout))

    with httpx.Client(timeout=timeout) as client:
        if args.resume_job_id:
            job = _resume(client, base_url, args.resume_job_id, force=args.force_resume)
            job_id = args.resume_job_id
        else:
            assert pdf_path is not None
            job = _upload(client, base_url, pdf_path, args.max_pdf_pages)
            job_id = str(job["job_id"])
        _write_json(output_dir / "job-submitted.json", job)
        print(f"[upload] job_id={job_id} status={job.get('status')}", flush=True)
        final_job = _poll_job(
            client,
            base_url,
            job_id,
            args.poll_seconds,
            args.wait_timeout,
            output_dir,
            args.download_retries,
        )
        _write_json(output_dir / "job.json", final_job)
        _download_artifacts(
            client,
            base_url,
            job_id,
            final_job,
            output_dir,
            args.download_retries,
            include_page_images=not args.no_page_images,
        )
        _write_stage_summaries(output_dir, final_job)
        _print_summary(output_dir, final_job)
    return 0 if final_job.get("status") in {"success", "partial"} else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the backend PDF Agent and collect step outputs.")
    parser.add_argument("pdf", type=Path, nargs="?", help="PDF drawing to upload")
    parser.add_argument("--resume-job-id", help="Resume failed batches for an existing backend job")
    parser.add_argument(
        "--force-resume",
        action="store_true",
        help="Resume a stale job whose manifest is still marked as processing",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend URL")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/backend-test"))
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--wait-timeout", type=float, default=24 * 60 * 60)
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument("--download-retries", type=int, default=5)
    parser.add_argument("--max-pdf-pages", type=int, default=0, help="0 means full PDF")
    parser.add_argument(
        "--no-page-images",
        action="store_true",
        help="Do not download the stage-one images grouped by Plant Function",
    )
    return parser.parse_args()


def _upload(client: httpx.Client, base_url: str, pdf_path: Path, max_pdf_pages: int) -> dict[str, Any]:
    url = urljoin(base_url, "api/v1/process/pdf")
    with pdf_path.open("rb") as stream:
        response = client.post(
            url,
            files={"file": (pdf_path.name, stream, "application/pdf")},
            data={"max_pdf_pages": str(max_pdf_pages)},
            timeout=httpx.Timeout(300.0, connect=30.0),
        )
    _raise_for_status(response, "upload")
    payload = response.json()
    return payload["job"]


def _resume(client: httpx.Client, base_url: str, job_id: str, *, force: bool = False) -> dict[str, Any]:
    url = urljoin(base_url, f"api/v1/library/{job_id}/resume")
    response = client.post(url, params={"force": str(force).lower()})
    _raise_for_status(response, "resume")
    return response.json()["job"]


def _poll_job(
    client: httpx.Client,
    base_url: str,
    job_id: str,
    poll_seconds: float,
    wait_timeout: float,
    output_dir: Path,
    download_retries: int,
) -> dict[str, Any]:
    url = urljoin(base_url, f"api/v1/library/{job_id}")
    started = time.monotonic()
    previous: tuple[Any, ...] | None = None
    while True:
        response = client.get(url)
        _raise_for_status(response, "poll")
        job = response.json()
        manifest = job.get("manifest") or {}
        diagnostics = manifest.get("grouping_raw") or {}
        state = (
            job.get("status"),
            job.get("status_message"),
            len(job.get("pages") or []),
            len(job.get("groups") or []),
            len(diagnostics.get("segments") or []),
            len(diagnostics.get("extraction_batches") or []),
            len(diagnostics.get("validation_warnings") or []),
            len(diagnostics.get("processed_pages") or []),
            len(diagnostics.get("wire_units") or {}),
            len(diagnostics.get("reference_queue") or []),
            len(diagnostics.get("reference_results") or {}),
            len(diagnostics.get("cross_page_tasks") or []),
            len(diagnostics.get("cross_page_results") or {}),
        )
        if state != previous:
            stage = _current_stage(diagnostics)
            print(
                "[step] stage={} status={} pages={} groups={} warnings={} "
                "scanned_pages={} wire_units={} cross_page={}/{} message={}".format(
                    stage,
                    state[0], state[2], state[3], state[6], state[7], state[8],
                    state[12], state[11], state[1] or ""
                ),
                flush=True,
            )
            _write_json(output_dir / "job-latest.json", job)
            _download_stage_files(
                client,
                base_url,
                job_id,
                output_dir,
                retries=download_retries,
                quiet=True,
            )
            previous = state
        if job.get("status") != "processing":
            return job
        if time.monotonic() - started > wait_timeout:
            raise TimeoutError(f"Backend job did not finish within {wait_timeout:g}s: {job_id}")
        time.sleep(max(0.1, poll_seconds))


def _download_artifacts(
    client: httpx.Client,
    base_url: str,
    job_id: str,
    job: dict[str, Any],
    output_dir: Path,
    retries: int,
    *,
    include_page_images: bool,
) -> None:
    _download_stage_files(client, base_url, job_id, output_dir, retries=retries)

    run_dir = output_dir / "00_run"
    run_dir.mkdir(parents=True, exist_ok=True)
    for filename in RUN_FILES:
        _download_if_present(
            client,
            urljoin(base_url, f"api/v1/library/{job_id}/agent/{filename}"),
            run_dir / filename,
            retries=retries,
        )

    stage1_dir = output_dir / "01_page_classification"
    _write_json(stage1_dir / "pages.json", job.get("pages") or [])
    if include_page_images:
        _download_page_images(client, base_url, job, stage1_dir / "pages", retries)

    stage3_dir = output_dir / "03_cross_page_completion"
    _download_if_present(
        client,
        urljoin(base_url, f"library/{job_id}/table.xlsx"),
        stage3_dir / "table.xlsx",
        retries=retries,
    )
    table_path = stage3_dir / "table.json"
    if not table_path.is_file():
        _write_json(
            table_path,
            {
                "headers": job.get("table_headers") or [],
                "rows": job.get("table_rows") or [],
            },
        )

    for group in job.get("groups") or []:
        group_id = str(group.get("group_id") or "group")
        group_dir = stage3_dir / "wire_units" / _safe_component(group_id)
        group_dir.mkdir(parents=True, exist_ok=True)
        for filename in (
            "records.json",
            "table.json",
            "source-pages.json",
        ):
            _download_if_present(
                client,
                urljoin(base_url, f"api/v1/library/{job_id}/groups/{group_id}/{filename}"),
                group_dir / filename,
                retries=retries,
            )


def _download_stage_files(
    client: httpx.Client,
    base_url: str,
    job_id: str,
    output_dir: Path,
    *,
    retries: int,
    quiet: bool = False,
) -> None:
    for stage_name, filenames in STAGE_FILES.items():
        stage_dir = output_dir / stage_name
        stage_dir.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            _download_if_present(
                client,
                urljoin(base_url, f"api/v1/library/{job_id}/agent/{filename}"),
                stage_dir / filename,
                retries=retries,
                quiet=quiet,
            )


def _download_page_images(
    client: httpx.Client,
    base_url: str,
    job: dict[str, Any],
    destination: Path,
    retries: int,
) -> None:
    for page in job.get("pages") or []:
        page_url = str(page.get("url") or "").strip()
        if not page_url:
            continue
        parsed = urlparse(page_url)
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        try:
            page_marker = parts.index("pages")
            relative_parts = parts[page_marker + 1 :]
        except ValueError:
            relative_parts = []
        if not relative_parts:
            function = _safe_component(str(page.get("drawing_function") or "unclassified"))
            filename = _safe_component(str(page.get("filename") or f"page-{page.get('page_number', 0)}.png"))
            relative_parts = [function, filename]
        relative_path = Path(*(_safe_component(part) for part in relative_parts))
        _download_if_present(
            client,
            urljoin(base_url, page_url),
            destination / relative_path,
            retries=retries,
        )


def _download_if_present(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    retries: int = 5,
    quiet: bool = False,
) -> bool:
    for attempt in range(max(0, retries) + 1):
        try:
            response = client.get(url)
            if response.status_code == 404:
                return False
            if response.status_code in {408, 429} or response.status_code >= 500:
                if attempt < retries:
                    time.sleep(min(30.0, 2.0 ** attempt))
                    continue
            _raise_for_status(response, f"download {url}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(response.content)
            if not quiet:
                print(f"[artifact] {destination}", flush=True)
            return True
        except httpx.RequestError:
            if attempt >= retries:
                raise
            time.sleep(min(30.0, 2.0 ** attempt))
    return False


def _print_summary(output_dir: Path, job: dict[str, Any]) -> None:
    groups = job.get("groups") or []
    print("\nFinal result", flush=True)
    print(f"  status: {job.get('status')}", flush=True)
    print(f"  pages: {job.get('page_count', 0)}", flush=True)
    print(f"  groups: {job.get('group_count', len(groups))}", flush=True)
    print(f"  records: {job.get('record_count', 0)}", flush=True)
    print(f"  stage 1: {output_dir / '01_page_classification'}", flush=True)
    print(f"  stage 2: {output_dir / '02_page_scan'}", flush=True)
    print(f"  stage 3: {output_dir / '03_cross_page_completion'}", flush=True)
    print(f"  final table: {output_dir / '03_cross_page_completion' / 'table.json'}", flush=True)
    print(f"  final xlsx: {output_dir / '03_cross_page_completion' / 'table.xlsx'}", flush=True)


def _current_stage(diagnostics: dict[str, Any]) -> str:
    if diagnostics.get("cross_page_tasks") or diagnostics.get("cross_page_results"):
        return "3/cross-page"
    if diagnostics.get("processed_pages") or diagnostics.get("page_scan_results"):
        return "2/page-scan"
    return "1/classification"


def _write_stage_summaries(output_dir: Path, job: dict[str, Any]) -> None:
    stage1 = output_dir / "01_page_classification"
    classifications = _read_json(stage1 / "page-classifications.json", {})
    function_groups = _read_json(stage1 / "plant-function-groups.json", {})
    _write_json(
        stage1 / "summary.json",
        {
            "pdf_pages": len(job.get("pages") or []),
            "classified_pages": len(classifications.get("classifications", classifications)) if isinstance(classifications, dict) else 0,
            "plant_function_groups": len(function_groups) if isinstance(function_groups, dict) else 0,
        },
    )

    stage2 = output_dir / "02_page_scan"
    page_results = _read_json(stage2 / "page-scan-results.json", {})
    wire_units = _read_json(stage2 / "wire-units.json", {})
    stage2_table = _read_json(stage2 / "stage2-table.json", {})
    rows_by_unit = stage2_table.get("rows_by_unit", {}) if isinstance(stage2_table, dict) else {}
    _write_json(
        stage2 / "summary.json",
        {
            "scanned_pages": len(page_results) if isinstance(page_results, dict) else 0,
            "wire_units": len(wire_units) if isinstance(wire_units, dict) else 0,
            "table_rows": sum(len(rows) for rows in rows_by_unit.values()) if isinstance(rows_by_unit, dict) else 0,
        },
    )

    stage3 = output_dir / "03_cross_page_completion"
    tasks = _read_json(stage3 / "cross-page-tasks.json", [])
    results = _read_json(stage3 / "cross-page-results.json", {})
    final_table = _read_json(stage3 / "table.json", {})
    final_rows_by_unit = final_table.get("rows_by_unit", {}) if isinstance(final_table, dict) else {}
    flat_rows = final_table.get("rows", []) if isinstance(final_table, dict) else []
    _write_json(
        stage3 / "summary.json",
        {
            "cross_page_tasks": len(tasks) if isinstance(tasks, list) else 0,
            "completed_cross_page_tasks": len(results) if isinstance(results, dict) else 0,
            "final_table_rows": (
                sum(len(rows) for rows in final_rows_by_unit.values())
                if isinstance(final_rows_by_unit, dict) and final_rows_by_unit
                else len(flat_rows) if isinstance(flat_rows, list) else 0
            ),
            "job_status": job.get("status"),
        },
    )


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _safe_component(value: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' or ord(char) < 32 else char for char in value).strip(" .")
    return cleaned or "unknown"


def _raise_for_status(response: httpx.Response, operation: str) -> None:
    if response.is_success:
        return
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    raise RuntimeError(f"{operation} failed: HTTP {response.status_code}: {detail}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, OSError, RuntimeError, TimeoutError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
