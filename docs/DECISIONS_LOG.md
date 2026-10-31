# Decisions log

The coding agent records any assumption or deviation from docs/SPEC.md here (date, what, why).

| Date | Decision | Why |
|---|---|---|
| 2026-10-31 | Upload with zero accepted files returns 422 with the same UploadResponse body (documents empty) | SPEC does not say; lets a client see every rejection code in one response |
| 2026-10-31 | Added error code TOO_MANY_FILES (422) when more than MAX_FILES_PER_UPLOAD files are sent | SPEC §4 defines the limit but no code for it |
| 2026-10-31 | If the Celery broker rejects the enqueue, the document is marked failed with INTERNAL_ERROR and Reprocess is offered | Otherwise the document would stay queued with no task |
| 2026-10-31 | `sniff()` receives the first 4 KB, not 8 bytes | CSV needs the text check over 4 KB (SPEC §6.1) |
| 2026-10-31 | `storage_path` holds the full path; `storage.open_path(storage_path)` takes the string | Simpler than deriving from STORAGE_DIR at read time |
| 2026-10-31 | Added `app/api/common.py` (pagination and invoice summary builder) and `app/pipeline/types.py` (shared stage data classes) | Several routers and stages share them; not in the SPEC §3 tree |
| 2026-10-31 | Added `app/pipeline/normalize.py` as the shared amount, date and name helpers (SPEC §5, §6.8) | Used by extraction, validation, search and cross-checks |
| 2026-10-31 | Ruff ignores B008 under app/api (FastAPI Depends and File defaults) | Those defaults are the FastAPI idiom, not a bug |
| 2026-10-31 | Tests run against native Postgres 16 + pgvector + Redis when Docker is unavailable; each parallel worker uses its own database | Keeps parallel test runs from truncating each other's tables |
| 2026-10-31 | Commits use the user's identity via environment variables, with no AI trailers | AGENTS.md forbids AI trailers; the build sandbox identity is not the user's |
