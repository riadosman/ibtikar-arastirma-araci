.PHONY: init up down seed test test-postgres lint migrate-check check live-check logs backup
PY ?= .venv/bin/python

init:
	python scripts/init_env.py
up:
	docker compose up --build -d
down:
	docker compose down
seed:
	docker compose exec backend python -m app.seed
# Unit + integration tests inside the running backend image (temporary SQLite).
test:
	docker compose exec backend python -m pytest -q
	docker compose exec backend python -m alembic check
# Same suite against a disposable PostgreSQL container.
test-postgres:
	docker rm -f rip-test-pg >/dev/null 2>&1 || true
	docker run -d --name rip-test-pg -e POSTGRES_PASSWORD=testpass -e POSTGRES_USER=test \
		-e POSTGRES_DB=test -p 127.0.0.1:15499:5432 --tmpfs /var/lib/postgresql/data postgres:17-alpine
	until docker exec rip-test-pg pg_isready -U test >/dev/null 2>&1; do sleep 1; done
	cd backend && TEST_DATABASE_URL=postgresql+psycopg://test:testpass@127.0.0.1:15499/test \
		../$(PY) -m pytest -q; status=$$?; docker rm -f rip-test-pg >/dev/null; exit $$status
lint:
	cd backend && ../$(PY) -m ruff check .
migrate-check:
	docker compose exec backend python -m alembic check
# Acceptance checks against the running deployment.
check:
	$(PY) scripts/production_check.py
live-check:
	$(PY) scripts/production_check.py --live --restart-worker
backup:
	$(PY) scripts/backup.py --verify
logs:
	docker compose logs -f backend worker
