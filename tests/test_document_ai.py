from pathlib import Path

from src.risk_intelligence_pipeline.document_ai import (
    Page,
    SectionSpec,
    parse_pdf_sections,
)


def test_parse_pdf_sections_maps_ocr_pages_to_sections(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.risk_intelligence_pipeline.document_ai._parse_pages",
        lambda pdf_path, config: ["risk page", "material page"],
    )

    sections = parse_pdf_sections(
        Path("not-used.pdf"),
        object(),
        [
            SectionSpec("Risk management", [50]),
            SectionSpec("Material impacts", [71]),
        ],
    )

    assert sections[0].pages == [Page(page_number=50, text="risk page")]
    assert sections[1].pages == [Page(page_number=71, text="material page")]
