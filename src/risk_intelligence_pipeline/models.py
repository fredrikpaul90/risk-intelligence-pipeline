"""Structured risk models — the contract between the LLM, the eval and the database."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RiskCategory(StrEnum):
    """Closed vocabulary. Free-text categories would break cross-company filtering."""

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    REGULATORY = "regulatory"
    MARKET = "market"
    CLIMATE = "climate"
    CYBER = "cyber"
    SUPPLY_CHAIN = "supply_chain"
    STRATEGIC = "strategic"
    PEOPLE = "people"
    OTHER = "other"


class SourceRef(BaseModel):
    """Provenance — every risk must be traceable back to a page an analyst can open."""

    model_config = ConfigDict(extra="forbid")

    section: str = Field(
        description=(
            "Name of the report section the risk was found in, e.g. 'Risk management'."
        )
    )
    page: int = Field(
        description="Printed page number shown on the page, not the PDF file index.",
        ge=1,
    )


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        description=(
            "Short risk title, at most 8 words, taken from or closely following the "
            "report's own wording."
        ),
        max_length=120,
    )
    description: str = Field(
        description=(
            "2-3 sentences describing the risk, grounded in the source text. "
            "No speculation."
        ),
        min_length=40,
    )
    category: RiskCategory = Field(
        description="Single best-fitting category from the closed vocabulary."
    )
    source: SourceRef
    mitigation: str | None = Field(
        description=(
            "The mitigating action the report states for this risk, summarised in "
            "1-2 sentences. Null if the report states none — do not invent one."
        )
    )
    evidence_quote: str = Field(
        description=(
            "A verbatim span of at least 10 words copied exactly from the source page, "
            "used as grounding/provenance to prove the risk is disclosed there and to "
            "reduce hallucinated or unsupported claims."
        ),
        min_length=30,
    )


class RiskList(BaseModel):
    """Per-section LLM response envelope (structured outputs need a root object)."""

    model_config = ConfigDict(extra="forbid")

    risks: list[Risk]
