# Changelog

## 2.0.0 (2026-10-28)

### Fixed
- The repository had been uploaded as a flat folder, so `backend.app.*` and `ingestion.*` imports could not
  resolve and same named files (`base.py`, `__init__.py`) had overwritten each other. The documented layout
  is restored and the lost provider neutral LLM interface and connector registry are recreated.
- Comma separated list settings (`RC_API_KEYS=a,b`) crashed settings loading.
- Vendor SDK errors surfaced as HTTP 500 because only `LLMUnavailableError` triggered the fallback.
- The extractive generator dropped the first line of a passage that had no section header.

### Added
- Clinical query understanding: brand names, US spellings, age, weight, medicines and intents.
- Deterministic tool routing with verified tool cards, streamed before generation.
- Medication safety screen (`/v1/tools/screen`) and rule file `knowledge/safety_rules.yaml`.
- Guideline supersession graph with ranking penalty, prompt marking and interface labels.
- Claim level faithfulness on every answer and an optional model judge for evaluation.
- Answerability gate based on IDF weighted question coverage.
- Provider router with ordered fallbacks and per vendor circuit breakers.
- In process LRU answer cache when Redis is unavailable; `cached` flag on responses.
- Keyed (HMAC) audit hashes, feedback endpoint and governance summary for admins.
- `/ready`, `/v1/understand`, `/v1/knowledge`, `/v1/tools/formulary` endpoints.
- `root-canon` CLI: `ask`, `understand`, `screen`, `serve`.
- Evaluation: 32 questions, faithfulness, scope and tool routing metrics, thresholds gate, markdown report.
- Interface: tool cards, patient context, safety screen tab, claim support chip, superseded labels,
  feedback and Markdown export of a consult.
- API Dockerfile, compose stack with Grafana dashboard and clinical safety alerts, GitHub Actions CI,
  dependabot, pre commit hooks, clinical safety hazard log and architecture decision records.

### Changed
- Security headers on every response, constant time API key comparison, `Retry-After` on rate limits.
- Offline evaluation: abstention accuracy 0.90 to 1.00, fact recall 0.82 to 0.94.
