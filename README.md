# Risk Intelligence Pipeline

Turns a corporate annual report (PDF) into structured, queryable principal-risk data:
title, description, category, source section/page, stated mitigation and evidence quote.

## Status

See [`PLAN.md`](PLAN.md), [`DESIGN.md`](DESIGN.md), and [`STRETCH.md`](STRETCH.md) for product context, architecture, and roadmap.

## Layout

```
annual_reports/   # source PDFs (gitignored, not tracked)
src/              # pipeline code (Document AI, extraction, Pydantic models)
eval/             # golden set + offline evaluator
tests/            # unit tests and cache/evaluation fixtures
output/           # generated OCR and extraction caches (gitignored)
PLAN.md           # product context and optimization target
DESIGN.md         # architecture and implementation trade-offs
STRETCH.md        # deferred roadmap
AGENTS.md         # repository conventions and commands
```

## Setup

```bash
uv sync
cp .env.example .env  # fill in project and processor settings
```

## Usage

### Configure Google Cloud

The active parser and extractor use Google Cloud Application Default Credentials. Copy `.env.example` to `.env`, fill in the project and Document AI processor identifiers, then authenticate locally with `gcloud auth application-default login`. `document_ai.py` loads `.env` automatically; shell commands do not need to export its values.

Create an OCR processor in Google Cloud Console under **Document AI** > **Processors**. Open the processor and copy its **Processor ID** into `DOCUMENT_AI_OCR_PROCESSOR_ID`. The processor location must match `GOOGLE_CLOUD_LOCATION`.

### Parse the PDF

Parse the already-trimmed PDF once and cache its text locally. `output/` is gitignored, so this does not create a tracked artifact or further Document AI costs when reused.

```bash
uv run python -m src.risk_intelligence_pipeline.document_ai \
  annual_reports/annual_report.pdf \
  --output output/document_ai/annual_report_parsed.json
```

The command writes one JSON object containing named report sections, original printed page numbers, and Document AI text. The default page mapping is pages 50-51 as `Risk management` and pages 71-74 as `Material impacts, risks, and opportunities`. Later pipeline stages should call `read_sections(Path("output/document_ai/annual_report_parsed.json"))` instead of `parse_pdf_sections()`.

### Extract Risks

Extract risks from a cached Document AI result. This calls Gemini once per parsed section and saves the validated JSON under gitignored `output/`. For demo stability, extraction defaults to `GEMINI_TEMPERATURE=0` and `GEMINI_SEED=0`; set those in `.env` only if you intentionally want different sampling behaviour.

```bash
uv run python -m src.risk_intelligence_pipeline.extract \
  output/document_ai/annual_report_parsed.json \
  --output output/extract/extracted_risks.json
```

### Evaluate the Output

Evaluate the extracted result against the hand-labelled golden set. This is fully offline and fails when required risks disappear, risks are invented, categories/pages change, or evidence no longer appears in the cached OCR text.

```bash
uv run python -m eval.evaluate \
  output/extract/extracted_risks.json \
  output/document_ai/annual_report_parsed.json
```

### Reproduce a Sample Failure

The included sample below reproduces a real category regression: a weaker prompt classified project execution as financial because its consequences included cost overruns. The command intentionally exits with status 1.

```bash
uv run python -m eval.evaluate \
  eval/sample_failure/weaker_model_risks.json \
  eval/sample_failure/parsed_sections.json \
  --golden eval/sample_failure/golden_risks.json
```

```text
FAIL:
- 'Project execution' has category <RiskCategory.FINANCIAL: 'financial'>; expected <RiskCategory.OPERATIONAL: 'operational'>.
```

### Run the Full Pipeline

Run the full pipeline. With no flags, it reuses both caches and runs evaluation only:

```bash
uv run python -m src.risk_intelligence_pipeline.pipeline
```

Use `--parse` and `--extract` together to refresh the complete pipeline. Use `--extract` alone to rerun extraction from the current parsed cache. These flags make the corresponding paid API calls; refreshing parsing without refreshing extraction is rejected because the two caches could refer to different source pages.

### Tests and Linting

```bash
uv run pytest
uv run ruff format src tests eval
uv run ruff check src
```
