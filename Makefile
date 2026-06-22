.PHONY: test init-db run-once run-ws refresh-instruments fetch-fng list-fng paper-fill-once ws-print ws-snapshot backtest-fetch backtest-csv api build run shell

test:
	PYTHONPATH=src pytest

init-db:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli init-db

run-once:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli run-once --symbol BTCUSDT

run-ws:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli run-ws --symbols BTCUSDT,ETHUSDT

refresh-instruments:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli refresh-instruments --symbols BTCUSDT,ETHUSDT

fetch-fng:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli fetch-fng --limit 30

list-fng:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli list-fng --limit 30

paper-fill-once:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli paper-fill-once --symbol BTCUSDT

ws-print:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli ws-print --symbols BTCUSDT --seconds 30 --orderbook-depth 1

ws-snapshot:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli ws-snapshot --symbols BTCUSDT --seconds 10

backtest-fetch:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli backtest-fetch --symbol BTCUSDT --interval 1 --start 2026-06-01 --end 2026-06-02

backtest-csv:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli backtest-csv --symbol BTCUSDT --input data/klines.csv

api:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli api --host 0.0.0.0 --port 8080

build:
	podman build -t adaptive-bybit-signal-bot -f Containerfile .

run:
	podman run --rm --env-file .env -v adaptive-bybit-data:/data adaptive-bybit-signal-bot

shell:
	podman run --rm -it --env-file .env -v adaptive-bybit-data:/data --entrypoint /bin/bash adaptive-bybit-signal-bot
