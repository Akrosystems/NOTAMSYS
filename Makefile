.PHONY: dev up down migrate seed test lint

dev:
	pnpm dev

up:
	docker compose up --build

down:
	docker compose down

migrate:
	cd apps/api && alembic upgrade head

seed:
	cd apps/api && python -m app.seed

test:
	cd apps/api && pytest && cd ../web && pnpm test

lint:
	cd apps/api && ruff check . && cd ../web && pnpm lint
