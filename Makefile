.PHONY: test init-db wait-db run-once run-ws refresh-instruments instrument-loop fetch-fng fng-loop list-fng paper-fill-once paper-loop ws-print ws-snapshot record-market replay-market backtest-fetch backtest-csv api build run shell compose-up compose-down compose-logs compose-recorder-up

test:
	PYTHONPATH=src pytest

init-db:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli init-db

wait-db:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli wait-db

run-once:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli run-once --symbol BTCUSDT

run-ws:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli run-ws --symbols BTCUSDT,ETHUSDT

refresh-instruments:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli refresh-instruments --symbols BTCUSDT,ETHUSDT

instrument-loop:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli instrument-loop --symbols BTCUSDT,ETHUSDT --once

fetch-fng:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli fetch-fng --limit 30

fng-loop:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli fng-loop --once

list-fng:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli list-fng --limit 30

paper-fill-once:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli paper-fill-once --symbol BTCUSDT

paper-loop:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli paper-loop --symbols BTCUSDT,ETHUSDT --once

ws-print:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli ws-print --symbols BTCUSDT --seconds 30 --orderbook-depth 1

ws-snapshot:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli ws-snapshot --symbols BTCUSDT --seconds 10

record-market:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli record-market --symbols BTCUSDT,ETHUSDT --seconds 300

replay-market:
	PYTHONPATH=src python -m adaptive_bybit_bot.cli replay-market --symbol BTCUSDT --input data/market-recordings/example.jsonl.gz

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

compose-up:
	./scripts/podman-compose-up.sh

compose-down:
	./scripts/podman-compose-down.sh

compose-logs:
	./scripts/podman-compose-logs.sh

compose-recorder-up:
	podman compose -f compose.yaml -f compose.recorder.yaml up --build postgres migrate api market-recorder
