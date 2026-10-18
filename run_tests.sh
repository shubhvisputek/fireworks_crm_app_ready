#!/usr/bin/env bash
# Runs every automated test: Python (API, services, legacy-database upgrade), frontend unit tests, and browser end-to-end.
set -euo pipefail
cd "$(dirname "$0")"

echo "== Python tests"
python3 -m unittest discover -s tests -t .

echo "== Frontend unit tests"
node --test tests/frontend/cart.test.mjs

echo "== Browser end-to-end test"
if node -e "require.resolve('playwright')" >/dev/null 2>&1 || [ -d "$(npm root -g 2>/dev/null)/playwright" ]; then
  node tests/e2e/app.e2e.mjs
else
  echo "Playwright is not installed; skipping (npm install -g playwright to enable)."
fi
