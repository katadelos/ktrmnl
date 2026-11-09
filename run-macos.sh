#!/bin/sh
set -eu

cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "ktrmnl2: install uv from https://docs.astral.sh/uv/" >&2
    exit 1
fi

exec uv run --python 3.11 ktrmnl2-sim --watch "$@"
