"""Parse a trimmed annual-report PDF with Google Cloud Document AI OCR."""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv
from google.api_core.client_options import ClientOptions
from google.cloud import documentai

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Page:
    """OCR text from one report page."""

    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class Section:
    name: str
    pages: list[Page]

    def as_prompt_text(self) -> str:
        return "\n\n".join(
            f"[page {page.page_number}]\n{page.text}" for page in self.pages
        )


@dataclass(frozen=True, slots=True)
class SectionSpec:
    name: str
    printed_page_numbers: list[int]


DEFAULT_SECTION_SPECS = (
    SectionSpec("Risk management", [50, 51]),
    SectionSpec("Material impacts, risks, and opportunities", [71, 72, 73, 74]),
)


class DocumentAiError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentAiConfig:
    project_id: str
    processor_id: str
    location: str = "eu"

    @classmethod
    def from_env(cls) -> DocumentAiConfig:
        """Load OCR processor configuration from a local .env file."""
        load_dotenv()
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        processor_id = os.environ.get("DOCUMENT_AI_OCR_PROCESSOR_ID")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "eu")
        if not project_id or not processor_id:
            raise DocumentAiError(
                "Set GOOGLE_CLOUD_PROJECT and DOCUMENT_AI_OCR_PROCESSOR_ID in .env."
            )
        return cls(
            project_id=project_id,
            processor_id=processor_id,
            location=location,
        )


def _ocr_page_text(
    document: documentai.Document, page: documentai.Document.Page
) -> str:
    """Read the OCR page layout anchor from the document-wide text field."""
    # Page text is stored as offsets into one document-wide OCR string.
    return "".join(
        document.text[int(segment.start_index) : int(segment.end_index)]
        for segment in page.layout.text_anchor.text_segments
    ).strip()


def _parse_pages(
    pdf_path: Path,
    config: DocumentAiConfig,
) -> list[str]:
    logger.info("[document_ai] sending %s to Document AI OCR processor", pdf_path)
    options = ClientOptions(api_endpoint=f"{config.location}-documentai.googleapis.com")
    client = documentai.DocumentProcessorServiceClient(client_options=options)
    # Send the PDF once; callers decide which printed pages map to the response.
    request = documentai.ProcessRequest(
        name=client.processor_path(
            config.project_id, config.location, config.processor_id
        ),
        raw_document=documentai.RawDocument(
            content=pdf_path.read_bytes(), mime_type="application/pdf"
        ),
    )
    document = client.process_document(request=request).document
    if not document.pages:
        raise DocumentAiError("OCR processor returned no pages.")
    # Preserve page boundaries for provenance and later evidence validation.
    return [_ocr_page_text(document, page) for page in document.pages]


def parse_pdf_sections(
    pdf_path: Path,
    config: DocumentAiConfig,
    section_specs: Sequence[SectionSpec] = DEFAULT_SECTION_SPECS,
) -> list[Section]:
    """Parse a trimmed PDF and group OCR pages into named report sections."""
    printed_page_numbers = [
        page_number
        for section_spec in section_specs
        for page_number in section_spec.printed_page_numbers
    ]
    if len(set(printed_page_numbers)) != len(printed_page_numbers):
        raise DocumentAiError("Configured printed page numbers must be unique.")
    page_texts = _parse_pages(pdf_path, config)
    if len(printed_page_numbers) != len(page_texts):
        raise DocumentAiError(
            "Received "
            f"{len(page_texts)} page(s) from OCR but "
            f"{len(printed_page_numbers)} printed page number(s) were configured."
        )
    # Flatten configured section ranges, then rebuild the named sections below.
    pages_by_number = {
        page_number: Page(page_number=page_number, text=text)
        for page_number, text in zip(printed_page_numbers, page_texts, strict=True)
    }
    return [
        Section(
            name=section_spec.name,
            pages=[
                pages_by_number[page_number]
                for page_number in section_spec.printed_page_numbers
            ],
        )
        for section_spec in section_specs
    ]


def write_sections(sections: Sequence[Section], output_path: Path) -> None:
    """Save parsed section text for later extraction without another OCR request."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"sections": [asdict(section) for section in sections]}, indent=2),
        encoding="utf-8",
    )


def read_sections(input_path: Path) -> list[Section]:
    """Load one or more previously cached Document AI sections."""
    if not input_path.exists():
        raise DocumentAiError(
            f"Parsed cache not found: {input_path}. Run document_ai.py to create it."
        )
    data = json.loads(input_path.read_text(encoding="utf-8"))
    logger.info("[document_ai] using cached parsed sections from %s", input_path)
    return [
        Section(
            name=section["name"],
            pages=[Page(**page) for page in section["pages"]],
        )
        for section in data["sections"]
    ]


def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output_path = (
        args.output or Path("output/document_ai") / "annual_report_parsed.json"
    )
    sections = parse_pdf_sections(
        args.pdf,
        DocumentAiConfig.from_env(),
    )
    write_sections(sections, output_path)
    page_count = sum(len(section.pages) for section in sections)
    print(
        f"Saved {page_count} parsed page(s) in "
        f"{len(sections)} section(s) to {output_path}"
    )


if __name__ == "__main__":
    _main()
