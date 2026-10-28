# Contributing

```bash
make install_dev      # Python dev dependencies, no model weights
make check            # ruff, README style, mypy, pytest with coverage, evaluation gate
```

## Rules that protect patients

1. **No number in code or prompts.** Doses, intervals and thresholds live in
   `backend/app/clinical/uk_dental_formulary.yaml` or come from a cited source. Never hard code one.
2. **Knowledge files are reviewed like code.** Changes to `backend/app/knowledge/*.yaml` must link the UK
   guidance they rest on, update the `reviewed` field and be approved by a registered clinician.
3. **The evaluation gate is not loosened to make a change pass.** If a threshold in
   `evaluation/thresholds.yaml` must move, explain why in the pull request.
4. **No patient data anywhere** in issues, tests, fixtures or logs. Use invented identifiers such as the
   NHS Digital example number 943 476 5919.

## Style

* Python 3.11+, ruff, mypy; line length 120.
* README prose uses British English and avoids hyphens and dashes (checked by `make lint`). Change the
  diagram in `docs/architecture.mmd` and run `make readme`.
* Add a golden question to `evaluation/golden_set.jsonl` for every new clinical behaviour.
