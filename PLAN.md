# Risk Database Product Plan

## User, Consumption & Product Surface
The users of the **structured, queryable risk database product** are analysts and clients, who can query the database to answer analytical questions. Querying certain risks directly will significantly speed up the analysts’ work, compared to reading the full reports.

The product’s scope has potential for extension. If the extracted risk records’ semantic meaning is embedded and stored in a Vector DB, the foundation for the retriever of a RAG based chatbot already exists. By generating the embedding of a question such as “What are the top enterprise risks facing Vestas?” and retrieving the most similar records from the Vector DB, an LLM can answer analysts’ and clients’ questions in natural language.

With 200+ corporate annual reports per quarter (averaging ~2.2 per day), an event-driven, trigger-based workflow for the structured, queryable risk database is entirely feasible. As soon as a new report enters the system, it triggers a request to the Risk Intelligence Pipeline, which directly uploads the processed record to the database. This automation requires the pipeline’s accuracy (see [Optimization Target](PLAN.md#optimization-target)) to be thoroughly validated before rollout.

A Cloud Run API is an ideal fit here: during idle periods, the service scales to zero, incurring zero compute costs. Even with a cold start, analysts will be able to query the newly processed risk data within 10 minutes of report ingestion. Once processing is complete, an automated alert can notify analysts that the new risk profile is ready to be reviewed.

## Optimization Target
This slice optimizes for
* **Extraction precision and groundedness**: do not invent risks or unsupported field values. Analysts rely on the output instead of re-reading the report, so each record must faithfully reflect and be verifiable against its cited source.
* **Extraction recall (coverage)**: do not miss principal risks present in the scoped sections.

In the [full pipeline](DESIGN.md#full-target-pipeline), section discovery should prioritize recall and pass uncertain pages
to extraction. Reviewing extra candidate pages costs tokens but dropping a relevant page
will permanently hide its risks from downstream extraction.

**Cost** and **throughput** are secondary at this volume: ~200 reports/quarter is low enough that neither LLM spend nor processing latency is a meaningful constraint. Even with a powerful LLM carrying out all the steps proposed in this repository (identify risk sections -> extract risks -> eval) the LLM cost would be ~$1 per report.

## Assumptions
* Analysts are available for consultation and quality review during the development phase, to validate output quality before automated rollout.
* The number of reports per quarter won't grow by orders of magnitude (not even during "report seasons"). If it does, cost and throughput may become concerns.
* New annual reports are stored in a centralized system. If they are manually downloaded by the analysts, a different interface may be more suitable (e.g. a UI where they can upload the file).

## Deferred Development and Future Product Aspirations
This is covered in detail in [STRETCH.md](STRETCH.md) but worth highlighting here are:
1. **Automated Section Discovery**: Identify the pages in annual reports that contain sections of interest (risk management, material impacts, risks etc). This is an integral component of the pipeline, but its development is intentionally deferred to avoid heavy Coding Agent and LLM credit usage and the case instruction to focus on certain sections of the PDF.
2. **MLOps**: Containerize the pipeline (Docker) and expose it via an HTTP API deployed to Cloud Run. Monitoring. CI/CD.
3. **Aspirational component reuse**: LLM-based RAG chatbot answering natural-language questions over the same risk database.
