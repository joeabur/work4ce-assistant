#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv --system-site-packages .venv
.venv/bin/python scripts/verify_dependencies.py
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pip check
