# AGENTS.md

Single source of truth for project conventions. Keep up to date as the pipeline is built.

## Stack
- **Language:** Python 3.13, `uv` for dependency management (no pip/poetry/conda).
- **Schema/validation:** Pydantic v2 (structured risk objects).
- **PDF parsing:** Google Cloud Document AI OCR (page-scoped text).
- **LLM:** Gemini on Vertex AI through `google-genai` (model is configurable).
- **Config:** `python-dotenv` (`.env`, never committed — see `.env.example`).
- **Testing/eval:** `pytest`.

## Commands
- **Setup:** `uv sync`
- **Run pipeline:** `uv run python -m src.risk_intelligence_pipeline.pipeline` (reuses caches by default)
- **Tests:** `uv run pytest`
- **Format/lint:** `uv run ruff format src tests eval` then `uv run ruff check src`
- **Add a dependency:** `uv add <pkg>` (or `uv add --dev <pkg>` for dev-only)

## Repository Layout

```
annual_reports/   # source PDFs — gitignored, never committed (large binaries)
src/              # pipeline code: Document AI (PDF → page text) → extract (LLM → structured risks) → schema (Pydantic models)
eval/             # golden set (hand-labeled expected risks) + evaluator(s)
tests/            # unit tests
PLAN.md           # product context: user, consumption surface, optimization target, assumptions, deferred scope
DESIGN.md         # stack, parsing/decomposition approach, trade-offs, scaling considerations
STRETCH.md        # what's next with more time
```

Status: `models.py`, `document_ai.py` (Document AI OCR page-scoped parsing), `extract.py` (Gemini structured extraction plus local provenance checks), `pipeline.py` (cache-aware orchestration), and `eval/evaluate.py` (offline golden-set regression evaluation) exist. Omitted from this slice: section discovery.

## Conventions
- **Line length:** Python source is limited to 88 characters (`[tool.ruff] line-length = 88`).
- **Markdown prose:** Use natural prose line lengths; do not hard-wrap paragraphs.
- **Modern typing:** `X | None`, `list[X]`, `dict[K, V]` — never `Optional`/`List`/`Dict`.
- **Secrets:** Google Cloud clients use Application Default Credentials; credential files and `.env` values are never committed. `.env.example` documents required identifiers.
- **Structured output:** every extracted risk is a validated Pydantic model, not raw LLM JSON — validate schema and provenance before accepting model output.
- **Provenance:** every extracted risk must carry the source section name and PDF page number it came from (traceability requirement from the case brief).
- **Scope:** Document AI is intentionally called only for Risk management p.50-51, Material impacts/risks/opportunities p.71-74 — do not build full-report section discovery in this slice.

## Gotchas
- **`pyproject.toml` has `[tool.uv] package = false`:** this is an application, not an installable library — don't add a `[build-system]`/`[project.scripts]` entry-point back in unless the project actually becomes a packaged CLI.
- **`annual_reports/` is gitignored:** source PDFs are never committed. If you need to reference report content in docs/tests, extract the relevant text/page snippets rather than checking in the PDF.
- **Printed page provenance:** `document_ai.py` maps OCR output to fixed section specs for the trimmed PDF: Risk management p.50-51 and Material impacts, risks, and opportunities p.71-74. The schema always stores the **printed** number, since that's what an analyst verifies against.
- **Document AI quality:** preserve page layout text anchors rather than flattening the document-wide text. Validate selected-page output against an annual-report fixture before changing processors or expanding the report set.
