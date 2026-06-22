from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from pathlib import Path
from typing import TextIO, cast

from adaptive_bybit_bot.recording.events import RecordedMarketEvent


class JsonlMarketEventWriter:
    """Append-only JSONL writer for recorded market events.

    If the path ends with ``.gz`` the stream is gzip-compressed. JSONL keeps the
    recording replayable even if the process is stopped mid-session.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = _open_text(self.path, "wt")
        self.event_count = 0

    def write(self, event: RecordedMarketEvent) -> None:
        self._fh.write(json.dumps(event.as_json(), separators=(",", ":"), ensure_ascii=False))
        self._fh.write("\n")
        self.event_count += 1

    def flush(self) -> None:
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()

    @property
    def bytes_written(self) -> int:
        try:
            self.flush()
            return self.path.stat().st_size
        except OSError:
            return 0

    def __enter__(self) -> JsonlMarketEventWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


def read_market_events(path: str | Path) -> Iterator[RecordedMarketEvent]:
    with _open_text(Path(path), "rt") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            value = json.loads(line)
            if isinstance(value, dict):
                yield RecordedMarketEvent.from_json(value)


def _open_text(path: Path, mode: str) -> TextIO:
    if path.suffix == ".gz":
        return cast(TextIO, gzip.open(path, mode, encoding="utf-8"))
    return cast(TextIO, path.open(mode, encoding="utf-8"))
