"""Extract validated risks from Document AI section text with Gemini."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .document_ai import Section, read_sections
from .models import Risk, RiskList

logger = logging.getLogger(__name__)

_CATEGORY_GUIDANCE = """Classify each risk by its primary driver, not by downstream
consequences such as cost, delay, or legal liability:
- financial: financing, liquidity, credit, currency, taxation/tariffs, or direct cost
    exposure not better explained by another category
- operational: project execution, manufacturing, quality, delivery, systems, or
    business continuity
- regulatory: compliance, misconduct, sanctions, or legal and regulatory obligations
- market: demand, pricing, competition, auctions, grid access, or market viability
- climate: physical or transition risks caused by climate change
- cyber: attacks, data compromise, or information-security failures
- supply_chain: supplier, component, material-availability, or logistics disruption
- strategic: long-term strategy, business-model, or investment-choice risk
- people: workforce health, safety, capability, attraction, or retention
- other: only when none of the categories above fits
Choose exactly one category. For example, project execution remains operational when
its consequences include cost overruns, and weak market conditions remain market when
their consequences include higher costs or delayed permits."""


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GeminiConfig:
    project_id: str
    location: str = "global"
    model: str = "gemini-3.5-flash-lite"
    temperature: float = 0
    seed: int = 0

    @classmethod
    def from_env(cls) -> GeminiConfig:
        """Load Vertex AI settings from the local .env file."""
        load_dotenv()
        project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ExtractionError("Set GOOGLE_CLOUD_PROJECT in .env.")
        return cls(
            project_id=project_id,
            location=os.environ.get("VERTEX_AI_LOCATION", "global"),
            model=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            temperature=float(os.environ.get("GEMINI_TEMPERATURE", "0")),
            seed=int(os.environ.get("GEMINI_SEED", "0")),
        )


def _normalise_text(text: str) -> str:
    return " ".join(text.lower().split())


def _prompt(section: Section) -> str:
    return f"""Extract every distinct disclosed risk from this annual-report section.

Return only risks explicitly supported by the supplied text. Use the source section name
exactly as provided, choose the page tag containing the evidence, and copy an evidence
quote verbatim from that same page. Do not infer missing risks, mitigations, or facts.
Return risks in the order they appear in the source text.

{_CATEGORY_GUIDANCE}

Section name: {section.name}

Source text:
{section.as_prompt_text()}
"""


def _validate_grounding(risks: Sequence[Risk], section: Section) -> None:
    """Verify each risk's section, page, and evidence quote against its source."""
    # Index source text by page so every generated quote can be checked locally.
    page_text: dict[int, str] = {}
    for page in section.pages:
        if page.page_number in page_text:
            raise ExtractionError(
                f"Section {section.name!r} contains duplicate page {page.page_number}."
            )
        page_text[page.page_number] = _normalise_text(page.text)
    for risk in risks:
        if risk.source.section != section.name:
            raise ExtractionError(
                f"Risk {risk.title!r} cites {risk.source.section!r}, expected "
                f"{section.name!r}."
            )
        source_text = page_text.get(risk.source.page)
        if source_text is None:
            raise ExtractionError(
                f"Risk {risk.title!r} cites page {risk.source.page}, which was not "
                "provided to Gemini."
            )
        if _normalise_text(risk.evidence_quote) not in source_text:
            raise ExtractionError(
                f"Risk {risk.title!r} has an evidence quote absent from its source "
                "page."
            )


def extract_section(
    section: Section,
    config: GeminiConfig,
    client: genai.Client | None = None,
) -> RiskList:
    """Extract and validate risks from a section using Gemini structured output."""
    logger.info(
        "[extract] calling Gemini (%s) for section %r", config.model, section.name
    )
    gemini = client or genai.Client(
        vertexai=True,
        project=config.project_id,
        location=config.location,
    )
    # Constrain the response to the Pydantic schema before applying source checks.
    response = gemini.models.generate_content(
        model=config.model,
        contents=_prompt(section),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=RiskList.model_json_schema(),
            temperature=config.temperature,
            seed=config.seed,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        ),
    )
    if not response.text:
        raise ExtractionError("Gemini returned no structured response text.")
    try:
        result = RiskList.model_validate_json(response.text)
    except ValueError as error:
        raise ExtractionError(
            "Gemini response did not satisfy the risk schema."
        ) from error
    # Schema validity is not enough: provenance must point back to supplied text.
    _validate_grounding(result.risks, section)
    return result


def extract_sections(sections: Sequence[Section], config: GeminiConfig) -> list[Risk]:
    """Extract all risks, making one schema-constrained request per source section."""
    return [
        risk for section in sections for risk in extract_section(section, config).risks
    ]


def write_risks(risks: RiskList, output_path: Path) -> None:
    """Save validated extraction output for reuse without another Gemini request."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(risks.model_dump_json(indent=2), encoding="utf-8")


def read_risks(input_path: Path) -> RiskList:
    """Load previously validated extraction output."""
    if not input_path.exists():
        raise ExtractionError(
            f"Extracted-risk cache not found: {input_path}. "
            "Run extract.py to create it."
        )
    # Revalidate cached JSON so stale or manually edited output cannot slip through.
    risks = RiskList.model_validate_json(input_path.read_text(encoding="utf-8"))
    logger.info("[extract] using cached extracted risks from %s", input_path)
    return risks


def _main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Cached Document AI JSON file.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sections = read_sections(args.input)
    output_path = args.output or Path("output/extract") / "extracted_risks.json"
    result = RiskList(risks=extract_sections(sections, GeminiConfig.from_env()))
    write_risks(result, output_path)
    print(f"Saved {len(result.risks)} extracted risk(s) to {output_path}")


if __name__ == "__main__":
    _main()
