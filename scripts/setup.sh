#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv --system-site-packages .venv
if ! .venv/bin/python scripts/verify_dependencies.py; then
  .venv/bin/python -m pip install -r requirements.lock
fi
.venv/bin/python scripts/verify_dependencies.py
if [ "${WORK4CE_BUILD_DASHBOARD:-1}" != "0" ]; then
  .venv/bin/python scripts/build_dashboard.py
fi
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pip check
