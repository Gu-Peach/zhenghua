from pathlib import Path

from backend.app.services.drawing_index import (
    DrawingIndex,
    DrawingPage,
    build_drawing_index,
    parse_drawing_page,
    parse_references,
)


def test_parse_page_header_and_cross_function_reference() -> None:
    page = parse_drawing_page(
        60,
        "=003.C\n1\nLOW VOLTAGE AC POWER\nObject Loc.:\n+01F11.1\n"
        "=080.C+01F12.1/10.1\n=.M+01F11.3/23.3",
    )
    refs = parse_references(page)

    assert page.function == "003.C"
    assert page.internal_page == 1
    assert page.object_loc == "+01F11.1"
    assert [(ref.target_function, ref.target_internal_page, ref.target_column) for ref in refs] == [
        ("080.C", 10, 1),
        ("003.M", 23, 3),
    ]


def test_index_resolves_non_contiguous_internal_pages_and_plans_bounded_batches() -> None:
    index = DrawingIndex(
        pdf_path="demo.pdf",
        pages=[
            DrawingPage(60, "003.C", 1, "+01F11.1"),
            DrawingPage(403, "080.C", 10, "+01F12.1"),
            DrawingPage(404, "080.C", 11, "+01F12.1"),
        ],
        page_lookup={"003.C:1": 60, "080.C:10": 403, "080.C:11": 404},
    )
    from backend.app.services.drawing_index import DrawingReference

    index.references = [
        DrawingReference(60, "080.C", 10, 1, "+01F12.1", "=080.C+01F12.1/10.1"),
        DrawingReference(60, "080.C", 11, 1, "+01F12.1", "=080.C+01F12.1/11.1"),
    ]
    assert index.referenced_pages(60) == [403, 404]
    batches = index.plan_batches(target_limit=1, include_unreferenced=False)
    assert [batch["target_pages"] for batch in batches] == [[403], [404]]


def test_build_peru_pdf_index_reads_full_document_and_stub() -> None:
    pdf = next((Path("case")).glob("*PERU*.pdf"), None)
    if pdf is None:
        return
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        try:
            import fitz  # noqa: F401
        except ImportError:
            import pytest
            pytest.skip("PyMuPDF is not installed in this test interpreter")
    index = build_drawing_index(pdf)
    assert len(index.pages) == 679
    assert len(index.page_lookup) > 500
    assert index.pages[0].is_non_wiring
    assert index.pages[2].is_non_wiring
    assert index.pages[59].function == "003.C"
    assert 403 in index.referenced_pages(60)
    assert index.pages[384].is_stub
    assert len(index.plan_batches(target_limit=4)) > 600
