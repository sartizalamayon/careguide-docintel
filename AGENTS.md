# Instructions for the coding agent

You are implementing **DocIntel**, an AI document intelligence system for a recruitment assessment. The design is finished. Your job is to implement it exactly, test it, and run the evaluation.

## Read first, in this order
1. `docs/SPEC.md`: every technical decision (stack, modules, prompts, rules, API, UI). **It is authoritative.**
2. `docs/PLAN.md`: milestones M1–M8, acceptance criteria, and the full list of test cases (U1–U43, I1–I20).
3. `docs/schema.sql`: the database. Migration `0001` already applies it.
4. `docs/DATASETS.md`: the labelled data under `datasets/eval/`. Use it for tests and evaluation.

## Rules
- **Follow the spec.** Do not swap libraries, add services, add auth systems, or add features that are not in SPEC.md. If something is ambiguous, pick the simplest option consistent with the spec and write one line in `docs/DECISIONS_LOG.md`.
- **Milestones in order.** Finish the acceptance criteria of a milestone before starting the next. Tick the milestone in `docs/PLAN.md` when it is done.
- **Tests are part of the work.** Write the tests listed for the milestone, in the same milestone. `make test` must be green before every commit. Tests never call a real LLM; use `FakeLLM` from `backend/tests/conftest.py`.
- **Never invent extracted values.** The extraction rules (null when absent, grounding check, flags) are the core requirement of the assessment. Do not "improve" them by computing missing fields.
- **Money is `Decimal`/`NUMERIC`, never float**, except at the LLM JSON boundary.
- **Keep it simple.** Small functions, type hints, no premature abstraction, no dead code, no commented-out code. Every module named in SPEC §3 exists. Do not add others unless needed.
- **Dependencies:** add a package only if SPEC names it. If you must, edit `backend/pyproject.toml` and run `make lock` (it regenerates `requirements*.txt`).
- **Secrets:** never commit `.env` or keys. The LLM key is read from env only.
- **Do not modify** `datasets/eval/**`, `docs/schema.sql` (unless a migration `0002` is added together with it) or the prompts in SPEC §6.7 without logging why.

## Git
- Commit with the git identity that is already configured on this machine. **Do not run `git config user.*`, do not pass `--author`, and do not add `Co-Authored-By` or other AI trailers.** AI assistance is disclosed in `docs/AI_DISCLOSURE.md` instead.
- Use small commits with conventional messages: `feat(api): document upload with magic-byte validation`, `test(validate): arithmetic rules`, `fix(ocr): ...`, `docs: evaluation results`.
- Push to `origin main` after each milestone.

## Commands
```bash
cp .env.example .env            # then set API_KEY and LLM_API_KEY
make up                         # build + start db, redis, api (runs migrations), worker, web
make logs                       # api + worker logs
make test                       # backend tests inside the api container
make lint                       # ruff + eslint
make data                       # download Katana ML images (needed for M8 and some tests)
make perf-data                  # 1000-page PDFs for the performance run
make eval / make eval-perf      # end-to-end evaluation -> eval/results/<timestamp>/
```
- API: http://localhost:8000/docs
- Web: http://localhost:3000
- Frontend dev: `cd frontend && cp .env.local.example .env.local && npm install && npm run dev`

## When you finish (M8)
- `docs/EVALUATION.md`: replace every TODO with numbers from `eval/results/<run>/metrics.json`.
- `README.md`: fill the "Results" table, and save 4 screenshots to `docs/screenshots/` (dashboard with uploads in progress, review page with issues, search, compare).
- `eval/results/test-report.txt`: output of `pytest -q --cov=app`.
- Make sure a fresh clone + `.env` + `make up` works by following the README only.
