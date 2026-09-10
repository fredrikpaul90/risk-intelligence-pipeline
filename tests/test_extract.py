import json
from pathlib import Path

from src.risk_intelligence_pipeline.document_ai import (
    DocumentAiError,
    Page,
    Section,
    SectionSpec,
    parse_pdf_sections,
    read_sections,
    write_sections,
)
from src.risk_intelligence_pipeline.extract import (
    GeminiConfig,
    extract_section,
)


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModels:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.last_kwargs: dict[str, object] = {}

    def generate_content(self, **kwargs: object) -> FakeResponse:
        self.last_kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response: FakeResponse) -> None:
        self.models = FakeModels(response)


def test_parse_pdf_sections_rejects_duplicate_printed_pages(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.risk_intelligence_pipeline.document_ai._parse_pages",
        lambda pdf_path, config: ["first", "second"],
    )

    try:
        parse_pdf_sections(
            Path("not-used.pdf"),
            object(),
            [SectionSpec("First", [50]), SectionSpec("Second", [50])],
        )
    except DocumentAiError as error:
        assert str(error) == "Configured printed page numbers must be unique."
    else:
        raise AssertionError("Expected duplicate printed pages to be rejected")


def test_extract_section_validates_a_quote_against_its_source_page() -> None:
    evidence = (
        "Supply-chain disruption could delay project delivery and increase costs."
    )
    section = Section(
        name="Risk management",
        pages=[Page(page_number=50, text=f"Principal risk: {evidence}")],
    )
    response = FakeResponse(
        json.dumps(
            {
                "risks": [
                    {
                        "title": "Supply-chain disruption",
                        "description": (
                            "Supply-chain disruption could delay project delivery and "
                            "increase costs for the company."
                        ),
                        "category": "supply_chain",
                        "source": {"section": "Risk management", "page": 50},
                        "mitigation": None,
                        "evidence_quote": evidence,
                    }
                ]
            }
        )
    )

    client = FakeClient(response)

    risks = extract_section(
        section,
        GeminiConfig(project_id="test-project"),
        client=client,  # type: ignore[arg-type]
    )

    assert risks.risks[0].title == "Supply-chain disruption"
    request_config = client.models.last_kwargs["config"]
    request_contents = client.models.last_kwargs["contents"]
    assert request_config.temperature == 0
    assert request_config.seed == 0
    assert request_config.automatic_function_calling.disable is True
    assert "primary driver" in request_contents
    assert "project execution remains operational" in request_contents
    assert "weak market conditions remain market" in request_contents


def test_sections_cache_round_trip(tmp_path: Path) -> None:
    sections = [
        Section(
            name="Risk management",
            pages=[Page(page_number=50, text="A disclosed enterprise risk.")],
        ),
        Section(
            name="Material impacts, risks, and opportunities",
            pages=[Page(page_number=71, text="A disclosed material risk.")],
        ),
    ]
    cache_path = tmp_path / "annual_report.json"

    write_sections(sections, cache_path)

    assert read_sections(cache_path) == sections
