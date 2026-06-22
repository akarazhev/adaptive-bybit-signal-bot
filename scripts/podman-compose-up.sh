#!/usr/bin/env sh
set -eu
PROVIDER=$(./scripts/compose-provider.sh)
# shellcheck disable=SC2086
exec $PROVIDER up --build "$@"
