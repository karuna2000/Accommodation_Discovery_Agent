.PHONY: dev build test lint clean shell

dev:
	docker compose up --build

build:
	docker compose build api

test:
	docker compose run --rm api pytest -v

lint:
	docker compose run --rm api ruff check src/ tests/

clean:
	docker compose down -v

shell:
	docker compose run --rm api bash
