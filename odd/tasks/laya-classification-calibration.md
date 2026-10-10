# Laya classification calibration

## Goal
Reduce noisy political categorizations from Laya by adding confidence handling and an evaluation path.

## Tasks
- [x] Add confidence threshold handling to the political classifier.
- [x] Represent low-confidence classifications as `uncertain` instead of forcing `political` / `not_political`.
- [x] Add an evaluation script and seed JSONL for political classification examples.
- [x] Update tests/docs for the new classification behavior.
- [x] Run focused checks and record evidence.

## Evidence
- Branch: `feat/laya-classification-calibration`
- Implemented `LAYA_POLITICAL_CONFIDENCE_THRESHOLD` with default `0.70`.
- Low-confidence Laya decisions now return label `uncertain` while preserving score.
- Added `backend/scripts/eval_classifications.py` and `eval_classifications_political_es.jsonl`.
- `python3 -m py_compile backend/app/classifications/political.py backend/scripts/eval_classifications.py` passed.
- `python3 backend/scripts/eval_classifications.py --help` passed.
- `git diff --check` passed.
- Focused pytest is blocked in the host Python environment by missing dependency `fastapi`; run it in Docker.
- Docker verification reported by user: `docker compose run --rm api sh -lc "pip install pytest httpx && python -m pytest tests/ -q"` collected 204 tests and passed all (`204 passed in 2.12s`). The trailing `sh: 2: -q: not found` came from a pasted newline after `tests/` and happened after pytest had already completed successfully.
