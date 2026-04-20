#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_DIR}"

echo "== Container proxy environment =="
docker compose exec app sh -lc 'env | grep -i proxy || true'

echo
echo "== Google reachability =="
docker compose exec app curl -sS --max-time 5 https://www.google.com -o /dev/null -w "%{http_code}\n"

echo
echo "== Anthropic domain reachability =="
docker compose exec app curl -sS --max-time 5 https://www.anthropic.com -o /dev/null -w "%{http_code}\n"

echo
echo "== Anthropic API endpoint probe =="
docker compose exec app sh -lc \
  "curl -sS --max-time 15 https://api.anthropic.com/v1/messages \
    -H 'x-api-key: test' \
    -H 'anthropic-version: 2023-06-01' \
    -H 'content-type: application/json' \
    -d '{}' \
    -o /dev/null -w '%{http_code}\n' || true"

echo
echo "== Zhipu domain reachability =="
docker compose exec app curl -sS --max-time 5 https://open.bigmodel.cn -o /dev/null -w "%{http_code}\n"

echo
echo "== Zhipu API endpoint probe =="
docker compose exec app sh -lc \
  "curl -sS --max-time 15 https://open.bigmodel.cn/api/paas/v4/chat/completions \
    -H 'Authorization: Bearer test' \
    -H 'content-type: application/json' \
    -d '{}' \
    -o /dev/null -w '%{http_code}\n' || true"

echo
echo "== Localhost NO_PROXY check =="
docker compose exec app sh -lc \
  "curl --noproxy '*' -sS --max-time 5 http://127.0.0.1:\${API_PORT:-8000}/health -o /dev/null -w '%{http_code}\n'"
