#!/usr/bin/env bash
# Run Nova offline unit tests (no API keys or network required).
set -euo pipefail
cd "$(dirname "$0")"
python3 -m unittest discover -s tests -v "$@"
