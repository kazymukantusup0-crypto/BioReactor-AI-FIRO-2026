# Farmer consultation review corpus

This is a separate staging area for possible future LoRA work. No training runs, model-weight changes or production model switches are performed. Prompt and orchestration edits are software development, not model training.

The existing real-Qwen QA traces can be exported with:

```powershell
python -X utf8 evaluations/export_farmer_training_candidates.py reports/qwen4b_manual_qa/limited_chat_TRACE.json --output datasets/farmer_consultant/candidates.jsonl
```

Every candidate retains the actual question, delivered answer, raw model synthesis, tool results, verification and immutable source trace hash. Canned-provider tests are not exportable as real inference. The user-supplied pig-slurry acceptance question and agent-authored unfamiliar validation questions have different origin labels; the latter are not real farmer traffic. All records are development data, pending independent scientific/source review, with `eligible_for_training=false`.

Before training: collect consented real farmer questions; review factual claims, units, applicability, cost assumptions and corrections independently; distinguish model answers from deterministic/fallback delivery; remove incomplete and unsupported targets; deduplicate multi-turn tasks by source/batch/session; prevent the same paper-derived task leaking across splits; reserve an untouched blind holdout; record reviewer and dataset version/hash. A few passed tool verifications are not a sufficient training-data quality assessment. Model training needs a separate resource and quality decision.
