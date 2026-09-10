"""Evaluate extracted risks against a hand-labelled golden set."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from src.risk_intelligence_pipeline.document_ai import Section, read_sections
from src.risk_intelligence_pipeline.models import RiskCategory, RiskList


class GoldenRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    page: int
    category: RiskCategory


class GoldenSet(BaseModel):
    """Treated as exhaustive for its report/page range: extra extracted risks fail."""

    model_config = ConfigDict(extra="forbid")

    required_risks: list[GoldenRisk]


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    failures: list[str]
    required_risks: int

    @property
    def passed(self) -> bool:
        return not self.failures


class EvaluationError(RuntimeError):
    pass


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def evaluate(
    extracted: RiskList, sections: Sequence[Section], golden: GoldenSet
) -> EvaluationResult:
    """Check recall, precision, expected labels, and evidence against source text.

    The golden set is treated as exhaustive for this fixed report/page range (see
    DESIGN.md), so any extracted risk with no matching golden title is a precision
    failure: either an invented risk or a duplicate split out of one golden risk.
    """
    failures: list[str] = []
    # Normalised titles make matching tolerant of case and whitespace differences.
    risks_by_title = {_normalise(risk.title): risk for risk in extracted.risks}
    # Recall and labels: every expected risk must be present with its expected page
    # and category.
    for expected in golden.required_risks:
        risk = risks_by_title.get(_normalise(expected.title))
        if risk is None:
            failures.append(f"Missing required risk: {expected.title!r}.")
            continue
        if risk.source.page != expected.page:
            failures.append(
                f"{expected.title!r} cites page {risk.source.page}; "
                f"expected {expected.page}."
            )
        if risk.category != expected.category:
            failures.append(
                f"{expected.title!r} has category {risk.category!r}; "
                f"expected {expected.category!r}."
            )

    # Precision: because the golden set is exhaustive, reject extra risk titles.
    golden_titles = {_normalise(expected.title) for expected in golden.required_risks}
    for risk in extracted.risks:
        if _normalise(risk.title) not in golden_titles:
            failures.append(f"Unexpected risk not in golden set: {risk.title!r}.")

    # Store each OCR page's section and text by page number for later checks. The same
    # page number cannot appear twice because then we would not know which text to use.
    page_text: dict[int, str] = {}
    page_section: dict[int, str] = {}
    for section in sections:
        for page in section.pages:
            if page.page_number in page_section:
                failures.append(
                    f"Page {page.page_number} is assigned to multiple sections: "
                    f"{page_section[page.page_number]!r} and {section.name!r}."
                )
                continue
            page_text[page.page_number] = _normalise(page.text)
            page_section[page.page_number] = section.name
    # Provenance: each risk must cite its actual OCR section and page, and quote text
    # that appears on that page.
    for risk in extracted.risks:
        source_text = page_text.get(risk.source.page)
        expected_section = page_section.get(risk.source.page)
        if expected_section is not None and risk.source.section != expected_section:
            failures.append(
                f"{risk.title!r} cites section {risk.source.section!r}; "
                f"expected {expected_section!r}."
            )
        if source_text is None:
            failures.append(
                f"{risk.title!r} cites unavailable page {risk.source.page}."
            )
        elif _normalise(risk.evidence_quote) not in source_text:
            failures.append(
                f"{risk.title!r} has an evidence quote absent from page "
                f"{risk.source.page}."
            )
    return EvaluationResult(
        failures=failures, required_risks=len(golden.required_risks)
    )


def _load_risks(path: Path) -> RiskList:
    if not path.exists():
        raise EvaluationError(
            f"Extracted-risk cache not found: {path}. Run extract.py to create it."
        )
    return RiskList.model_validate_json(path.read_text(encoding="utf-8"))


def _load_golden_set(path: Path) -> GoldenSet:
    if not path.exists():
        raise EvaluationError(f"Golden set not found: {path}.")
    return GoldenSet.model_validate_json(path.read_text(encoding="utf-8"))


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted", type=Path, help="Validated Gemini output JSON.")
    parser.add_argument("parsed", type=Path, help="Cached Document AI output JSON.")
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path("eval/golden_risks.json"),
        help="Hand-labelled required risks.",
    )
    args = parser.parse_args()
    result = evaluate(
        _load_risks(args.extracted),
        read_sections(args.parsed),
        _load_golden_set(args.golden),
    )
    if result.passed:
        print(f"PASS: {result.required_risks} required risks matched.")
        return
    print("FAIL:")
    for failure in result.failures:
        print(f"- {failure}")
    raise SystemExit(1)


if __name__ == "__main__":
    _main()
