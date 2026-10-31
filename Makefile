.PHONY: help up down logs migrate test lint data perf-data eval eval-perf lock web-dev

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

up:              ## build and start everything (db, redis, api, worker, web)
	docker compose up -d --build

down:            ## stop everything (keeps data volumes)
	docker compose down

logs:            ## follow api + worker logs
	docker compose logs -f api worker

migrate:         ## apply database migrations
	docker compose exec api alembic upgrade head

test:            ## run the backend test suite inside the api container
	docker compose exec -e CELERY_TASK_ALWAYS_EAGER=true api pytest -q --cov=app --cov-report=term-missing

lint:            ## ruff + frontend lint
	docker compose exec api ruff check app tests
	cd frontend && npm run lint

DATASET_RUN = docker run --rm -v "$(CURDIR)/datasets:/datasets" -w /datasets python:3.12-slim \
	sh -c "pip install -q -r requirements.txt && python tools/$(1)"

data:            ## download + convert the public labelled set (Katana ML, ~90 MB) - runs in a throwaway container
	$(call DATASET_RUN,fetch_katanaml.py)

perf-data:       ## generate the 1000-page performance PDFs (~60 MB, gitignored)
	$(call DATASET_RUN,generate_synthetic.py --perf)

eval:            ## run the end-to-end evaluation against the running stack (results -> eval/results/<timestamp>)
	docker compose exec -w / api python -m eval.run_eval --api http://localhost:8000 \
	  --manifests /datasets/eval/manifest_synthetic.jsonl /datasets/eval/manifest_katanaml.jsonl \
	  --out /eval/results/$$(date +%Y%m%d-%H%M)

eval-perf:       ## run the 1000-page performance evaluation (needs `make perf-data` first)
	docker compose exec -w / api python -m eval.run_eval --api http://localhost:8000 \
	  --manifests /datasets/eval/manifest_perf.jsonl --out /eval/results/perf-$$(date +%Y%m%d-%H%M)

lock:            ## re-export pinned requirements after changing backend/pyproject.toml
	cd backend && uv lock && uv export --frozen --no-dev --no-emit-project -o requirements.txt -q \
	  && uv export --frozen --only-group dev --no-emit-project -o requirements-dev.txt -q

web-dev:         ## run the frontend in dev mode against the dockerised API
	cd frontend && npm run dev
