#!/usr/bin/env sh
set -eu
if command -v podman >/dev/null 2>&1; then
  if podman compose version >/dev/null 2>&1; then
    echo "podman compose"
    exit 0
  fi
fi
if command -v podman-compose >/dev/null 2>&1; then
  echo "podman-compose"
  exit 0
fi
echo "podman compose provider not found. Install podman-compose or configure podman compose." >&2
exit 1
