from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from sqlalchemy.engine import make_url

from adaptive_bybit_bot.config import Settings


def test_default_sqlite_database_url_targets_data_volume() -> None:
    settings = Settings(**cast(Any, {"_env_file": None}))

    assert settings.database_url == "sqlite:////data/bot.db"
    assert make_url(settings.database_url).database == "/data/bot.db"
    assert "DATABASE_URL=sqlite:////data/bot.db" in Path(".env.example").read_text()
    assert "DATABASE_URL=sqlite:////data/bot.db" in Path("Containerfile").read_text()


def test_python_baseline_is_consistent_across_runtime_surfaces() -> None:
    first_line = Path("Containerfile").read_text().splitlines()[0]

    assert first_line == "FROM docker.io/python:3.14-slim"
    assert 'requires-python = ">=3.14"' in Path("pyproject.toml").read_text()
    assert 'python_version = "3.14"' in Path("pyproject.toml").read_text()
    assert 'python-version: "3.14"' in Path(".github/workflows/ci.yml").read_text()
    assert "Python 3.14" in Path("AGENTS.md").read_text()
    assert "Python 3.14" in Path("openspec/config.yaml").read_text()


def test_compose_postgres_healthcheck_uses_configured_identity() -> None:
    compose = Path("compose.yaml").read_text()

    assert "pg_isready" in compose
    assert "$${POSTGRES_USER:-bot}" in compose
    assert "$${POSTGRES_DB:-bybit_bot}" in compose
    assert "pg_isready -U bot -d bybit_bot" not in compose


def test_starlette_testclient_uses_httpx2_dependency() -> None:
    pyproject = Path("pyproject.toml").read_text()
    import_check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import warnings\n"
                "from starlette.exceptions import StarletteDeprecationWarning\n"
                "warnings.simplefilter('error', StarletteDeprecationWarning)\n"
                "import fastapi.testclient\n"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert '"httpx2>=2.4.0"' in pyproject
    assert importlib.util.find_spec("httpx2") is not None
    assert import_check.returncode == 0, import_check.stderr
