.PHONY: test run-once init-db build run shell api

test:
	PYTHONPATH=src pytest

init-db:
	PYTHONPATH=src adaptive-bybit-bot init-db

run-once:
	PYTHONPATH=src adaptive-bybit-bot run-once --symbol BTCUSDT

api:
	PYTHONPATH=src adaptive-bybit-bot api --host 0.0.0.0 --port 8080

build:
	podman build -t adaptive-bybit-signal-bot -f Containerfile .

run:
	podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot

shell:
	podman run --rm -it --env-file .env -v adaptive-bybit-data:/data --entrypoint /bin/bash adaptive-bybit-signal-bot
