.PHONY: test run-once init-db build run shell api refresh-instruments paper-fill-once ws-print

test:
	PYTHONPATH=src pytest

init-db:
	PYTHONPATH=src adaptive-bybit-bot init-db

run-once:
	PYTHONPATH=src adaptive-bybit-bot run-once --symbol BTCUSDT

refresh-instruments:
	PYTHONPATH=src adaptive-bybit-bot refresh-instruments --symbols BTCUSDT,ETHUSDT

paper-fill-once:
	PYTHONPATH=src adaptive-bybit-bot paper-fill-once --symbol BTCUSDT

ws-print:
	PYTHONPATH=src adaptive-bybit-bot ws-print --symbols BTCUSDT --seconds 30 --orderbook-depth 1

api:
	PYTHONPATH=src adaptive-bybit-bot api --host 0.0.0.0 --port 8080

build:
	podman build -t adaptive-bybit-signal-bot -f Containerfile .

run:
	podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot

shell:
	podman run --rm -it --env-file .env -v adaptive-bybit-data:/data --entrypoint /bin/bash adaptive-bybit-signal-bot
