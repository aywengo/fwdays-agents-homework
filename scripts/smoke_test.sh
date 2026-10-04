#!/usr/bin/env bash
# Post-start checks for the Docker deployment (no model tokens spent).
set -uo pipefail
cd "$(dirname "$0")/.."
ok() { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=1; }
FAIL=0
echo "Containers"; docker compose ps --format '{{.Service}}: {{.State}} {{.Health}}'
echo "Gateway"
curl -fsS -o /dev/null http://127.0.0.1:18789/healthz && ok "healthz" || bad "healthz"
curl -fsS http://127.0.0.1:18789/.well-known/agent-card.json | grep -q '"dispatcher"' && ok "A2A agent card lists dispatcher" || bad "A2A agent card"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:18789/a2a/v1 -H 'Content-Type: application/json' -d '{}')
[[ "$code" == 401 ]] && ok "A2A rejects unauthenticated calls" || bad "A2A auth (got $code)"
echo "OpenClaw"
docker compose exec -T openclaw openclaw config validate >/dev/null && ok "config valid" || bad "config validate"
docker compose exec -T openclaw openclaw mcp probe 2>&1 | grep -E "^[-!] " | sed 's/^/  /'
docker compose exec -T openclaw openclaw agents list 2>&1 | sed -n '1,12p' | sed 's/^/  /'
echo "Observability"
curl -fsS -o /dev/null http://127.0.0.1:3000/api/health && ok "Grafana http://127.0.0.1:3000" || bad "Grafana"
exit $FAIL
