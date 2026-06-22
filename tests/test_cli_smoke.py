from __future__ import annotations

from typer.testing import CliRunner

from adaptive_bybit_bot.cli import app


def test_cli_help_imports_cleanly() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "backtest-csv" in result.output
    assert "run-ws" in result.output
    assert "ws-snapshot" in result.output
    assert "ws-book" in result.output
    assert "fng-loop" in result.output
    assert "instrument-loop" in result.output
    assert "paper-loop" in result.output
    assert "list-services" in result.output
    assert "list-locks" in result.output
