from pathlib import Path

import pytest

from eval.evaluate import GoldenRisk, GoldenSet
from src.risk_intelligence_pipeline.document_ai import Page, Section, write_sections
from src.risk_intelligence_pipeline.extract import write_risks
from src.risk_intelligence_pipeline.models import (
    Risk,
    RiskCategory,
    RiskList,
    SourceRef,
)
from src.risk_intelligence_pipeline.pipeline import PipelineError, run_pipeline


def test_models_module_is_available() -> None:
    assert RiskList.model_validate({"risks": []}).risks == []


def test_pipeline_reuses_caches_and_evaluates_offline(tmp_path: Path) -> None:
    quote = "Cyber attacks could disrupt energy production and business operations."
    section = Section("Risk management", [Page(51, quote)])
    risks = RiskList(
        risks=[
            Risk(
                title="Cyber attacks",
                description=quote,
                category=RiskCategory.CYBER,
                source=SourceRef(section="Risk management", page=51),
                mitigation=None,
                evidence_quote=quote,
            )
        ]
    )
    golden = GoldenSet(
        required_risks=[
            GoldenRisk(title="Cyber attacks", page=51, category=RiskCategory.CYBER)
        ]
    )
    parsed_cache = tmp_path / "annual_report_parsed.json"
    extracted_cache = tmp_path / "extracted_risks.json"
    golden_path = tmp_path / "golden.json"
    write_sections([section], parsed_cache)
    write_risks(risks, extracted_cache)
    golden_path.write_text(golden.model_dump_json(), encoding="utf-8")

    result = run_pipeline(
        Path("not-used.pdf"),
        parsed_cache,
        extracted_cache,
        golden_path,
    )

    assert result == risks


def test_pipeline_rejects_parse_without_extract(tmp_path: Path) -> None:
    with pytest.raises(PipelineError, match="requires --extract"):
        run_pipeline(
            Path("not-used.pdf"),
            tmp_path / "parsed.json",
            tmp_path / "extracted.json",
            tmp_path / "golden.json",
            parse=True,
        )
