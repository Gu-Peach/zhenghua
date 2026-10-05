from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import StreamingResponse

from ...schemas.wire import ExportRequest, ExtractionResponse
from ...services.excel_writer import records_to_xlsx_bytes
from ...services.extraction_service import extract_from_uploads


router = APIRouter(prefix="/api/v1", tags=["wires"])


@router.post("/extract/wires", response_model=ExtractionResponse)
async def extract_wires(
    files: list[UploadFile] = File(...),
    model: str | None = Form(default=None),
    base_url: str | None = Form(default=None),
    api_key: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
    max_pdf_pages: int | None = Form(default=None),
) -> ExtractionResponse:
    records, sources = await extract_from_uploads(
        files=files,
        model=model,
        base_url=base_url,
        api_key=api_key,
        prompt=prompt,
        max_pdf_pages=max_pdf_pages,
    )
    return ExtractionResponse(record_count=len(records), records=records, sources=sources)


@router.post("/extract/wires/xlsx")
async def extract_wires_xlsx(
    files: list[UploadFile] = File(...),
    model: str | None = Form(default=None),
    base_url: str | None = Form(default=None),
    api_key: str | None = Form(default=None),
    prompt: str | None = Form(default=None),
    max_pdf_pages: int | None = Form(default=None),
    sheet_title: str = Form(default="放线表"),
) -> StreamingResponse:
    records, _ = await extract_from_uploads(
        files=files,
        model=model,
        base_url=base_url,
        api_key=api_key,
        prompt=prompt,
        max_pdf_pages=max_pdf_pages,
    )
    return _xlsx_response(records_to_xlsx_bytes(records, sheet_title=sheet_title), filename="wiring-table.xlsx")


@router.post("/wires/xlsx")
async def export_wires_xlsx(request: ExportRequest) -> StreamingResponse:
    filename = request.filename or "wiring-table.xlsx"
    content = records_to_xlsx_bytes(request.records, sheet_title=request.sheet_title or "放线表")
    return _xlsx_response(content, filename=filename)


def _xlsx_response(content: bytes, *, filename: str) -> StreamingResponse:
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )

