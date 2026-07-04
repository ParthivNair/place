.PHONY: db-up migrate seed seed-demo evaluate api test lint vapid

db-up:
	docker compose up -d --build

migrate:
	cd backend && .venv/bin/alembic upgrade head

seed:
	cd backend && .venv/bin/python -m place.ingest.cli overpass --limit 300
	cd backend && .venv/bin/python -m place.ingest.cli gnis
	cd backend && .venv/bin/python -m place.ingest.cli bindings

# Founder demo publication: founder_verified claims + publish for the
# NON-hazard launch affordances (wild-swim stays gated — correct behavior).
seed-demo:
	cd backend && .venv/bin/python -m place.ingest.cli seed-demo

evaluate:
	cd backend && .venv/bin/python -m place.evaluator.run --once

api:
	cd backend && .venv/bin/uvicorn place.api.app:app --reload --port 8000

test:
	cd backend && .venv/bin/python -m pytest -q

lint:
	cd backend && .venv/bin/ruff check place tests

# Prints VAPID_* lines ready to paste into .env (SUBJECT=mailto:you@example.com to override)
vapid:
	cd backend && .venv/bin/python -m place.api.vapid_keygen --subject $(or $(SUBJECT),mailto:admin@example.com)
