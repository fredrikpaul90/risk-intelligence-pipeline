"""Run OCR parsing, Gemini extraction, and offline regression evaluation."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from eval.evaluate import GoldenSet, evaluate

from .document_ai import (
    DEFAULT_SECTION_SPECS,
    DocumentAiConfig,
    Section,
    SectionSpec,
    parse_pdf_sections,
    read_sections,
    write_sections,
)
from .extract import GeminiConfig, extract_sections, read_risks, write_risks
from .models import RiskList

DEFAULT_PARSED_CACHE = Path("output/document_ai/annual_report_parsed.json")
DEFAULT_EXTRACTED_CACHE = Path("output/extract/extracted_risks.json")
DEFAULT_GOLDEN_SET = Path("eval/golden_risks.json")
DEFAULT_PDF = Path("annual_reports/annual_report.pdf")

logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    pass


def _read_golden_set(path: Path) -> GoldenSet:
    return GoldenSet.model_validate_json(path.read_text(encoding="utf-8"))


def run_pipeline(
    pdf_path: Path,
    parsed_cache: Path,
    extracted_cache: Path,
    golden_set: Path,
    *,
    parse: bool = False,
    extract: bool = False,
    section_specs: Sequence[SectionSpec] = DEFAULT_SECTION_SPECS,
) -> RiskList:
    """Run selected paid stages, reuse caches otherwise, then evaluate offline."""
    if parse and not extract:
        raise PipelineError(
            "Refreshing the parsed cache requires --extract as well so the "
            "extracted-risk cache cannot refer to different source pages."
        )
    sections: list[Section]
    logger.info("[document_ai] stage starting")
    if parse:
        # OCR is paid, so only run it when explicitly requested.
        logger.info("[document_ai] calling Document AI OCR (parsing %s)", pdf_path)
        sections = parse_pdf_sections(
            pdf_path,
            DocumentAiConfig.from_env(),
            section_specs,
        )
        write_sections(sections, parsed_cache)
    elif parsed_cache.exists():
        # Reuse the last OCR result for local development and evaluation.
        sections = read_sections(parsed_cache)
    else:
        raise PipelineError(
            f"Parsed cache not found: {parsed_cache}. Run with --parse."
        )

    logger.info("[extract] stage starting")
    if extract:
        # Gemini is also paid; write its validated result for later runs.
        logger.info("[extract] calling Gemini for structured risk extraction")
        risks = RiskList(risks=extract_sections(sections, GeminiConfig.from_env()))
        write_risks(risks, extracted_cache)
    elif extracted_cache.exists():
        # Cached risks still pass through Pydantic validation when loaded.
        risks = read_risks(extracted_cache)
    else:
        raise PipelineError(
            f"Extracted-risk cache not found: {extracted_cache}. Run with --extract."
        )

    logger.info(
        "[evaluate] stage starting (%d risk(s) against golden set)", len(risks.risks)
    )
    # Evaluation is offline: compare the cached or freshly extracted risks to labels.
    evaluation = evaluate(risks, sections, _read_golden_set(golden_set))
    if not evaluation.passed:
        raise PipelineError("Evaluation failed:\n- " + "\n- ".join(evaluation.failures))
    logger.info("[evaluate] passed")
    return risks


def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", nargs="?", type=Path, default=DEFAULT_PDF)
    parser.add_argument(
        "--parse", action="store_true", help="Run paid Document AI OCR."
    )
    parser.add_argument(
        "--extract", action="store_true", help="Run paid Gemini extraction."
    )
    parser.add_argument("--parsed-cache", type=Path, default=DEFAULT_PARSED_CACHE)
    parser.add_argument("--extracted-cache", type=Path, default=DEFAULT_EXTRACTED_CACHE)
    parser.add_argument("--golden-set", type=Path, default=DEFAULT_GOLDEN_SET)
    args = parser.parse_args()
    risks = run_pipeline(
        args.pdf,
        args.parsed_cache,
        args.extracted_cache,
        args.golden_set,
        parse=args.parse,
        extract=args.extract,
    )
    print(f"PASS: pipeline produced {len(risks.risks)} validated risk(s).")


if __name__ == "__main__":
    _main()
