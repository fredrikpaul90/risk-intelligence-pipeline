from pathlib import Path

from eval.evaluate import GoldenRisk, GoldenSet, evaluate
from src.risk_intelligence_pipeline.document_ai import Page, Section, read_sections
from src.risk_intelligence_pipeline.models import (
    Risk,
    RiskCategory,
    RiskList,
    SourceRef,
)

SAMPLE_FAILURE = Path("eval/sample_failure")


def _risk(*, quote: str, category: RiskCategory = RiskCategory.CYBER) -> Risk:
    return Risk(
        title="Cyber attacks",
        description=(
            "Cyber attacks could disrupt energy production and business operations."
        ),
        category=category,
        source=SourceRef(section="Risk management", page=51),
        mitigation=None,
        evidence_quote=quote,
    )


def test_evaluation_passes_for_matching_risk_and_evidence() -> None:
    quote = "Cyber attacks could disrupt energy production and business operations."
    section = Section("Risk management", [Page(51, quote)])
    golden = GoldenSet(
        required_risks=[
            GoldenRisk(title="Cyber attacks", page=51, category=RiskCategory.CYBER)
        ]
    )

    result = evaluate(RiskList(risks=[_risk(quote=quote)]), [section], golden)

    assert result.passed


def test_evaluation_catches_missing_risk_and_ungrounded_quote() -> None:
    section = Section("Risk management", [Page(51, "Source text on the page.")])
    golden = GoldenSet(
        required_risks=[
            GoldenRisk(
                title="Project execution", page=51, category=RiskCategory.OPERATIONAL
            )
        ]
    )

    result = evaluate(
        RiskList(risks=[_risk(quote="A quote that is not in the source text.")]),
        [section],
        golden,
    )

    assert any("Missing required risk" in failure for failure in result.failures)
    assert any("evidence quote absent" in failure for failure in result.failures)


def test_evaluation_catches_unexpected_risk_not_in_golden_set() -> None:
    quote = "Cyber attacks could disrupt energy production and business operations."
    section = Section("Risk management", [Page(51, quote)])
    golden = GoldenSet(required_risks=[])

    result = evaluate(RiskList(risks=[_risk(quote=quote)]), [section], golden)

    assert "Unexpected risk not in golden set: 'Cyber attacks'." in result.failures


def test_sample_failure_catches_category_regression() -> None:
    extracted = RiskList.model_validate_json(
        (SAMPLE_FAILURE / "weaker_model_risks.json").read_text(encoding="utf-8")
    )
    golden = GoldenSet.model_validate_json(
        (SAMPLE_FAILURE / "golden_risks.json").read_text(encoding="utf-8")
    )
    sections = read_sections(SAMPLE_FAILURE / "parsed_sections.json")

    result = evaluate(extracted, sections, golden)

    assert not result.passed
    assert len(result.failures) == 1
    assert "Project execution" in result.failures[0]
    assert "RiskCategory.FINANCIAL" in result.failures[0]
    assert "RiskCategory.OPERATIONAL" in result.failures[0]
