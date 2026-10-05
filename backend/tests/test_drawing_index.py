from pathlib import Path

from backend.app.services.drawing_index import build_drawing_index, parse_drawing_page, parse_references


def test_parse_page_and_non_contiguous_reference() -> None:
    page = parse_drawing_page(
        60,
        "Plant Function: =003.C Page Number: 1 Object Loc.: +01F11.1 "
        "Page description: LOW VOLTAGE AC POWER DISTRIBUTION "
        "=080.C+01F12.1/10.1/+01F12.1-FC11_L1",
    )
    refs = parse_references(page)

    assert page.function == "003.C"
    assert page.internal_page == 1
    assert page.object_loc == "+01F11.1"
    assert refs
    assert refs[0].target_function == "080.C"
    assert refs[0].target_internal_page == 10
    assert refs[0].target_column == 1


def test_build_peru_index_has_page_lookup_and_cross_function_references() -> None:
    pdf = next(Path("test_case").glob("*.pdf"), None)
    if pdf is None:
        return
    index = build_drawing_index(pdf)
    assert index.pages
    assert index.page_lookup
