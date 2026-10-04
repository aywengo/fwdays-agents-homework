#!/usr/bin/env bash
# Create the morning/evening report automations for the dispatcher.
# Usage: scripts/setup_automations.sh            (create missing jobs)
#        scripts/setup_automations.sh --list     (show jobs)
# Each job runs in an isolated session, is capped to read-only tools (no battery
# control), and announces the final reply to every configured report channel.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
oc() { docker compose exec -T openclaw openclaw "$@"; }

if [[ "${1:-}" == "--list" ]]; then oc automations list; exit 0; fi

TZ_NAME="${HOME_TZ:-Europe/Warsaw}"
# Read-only cap for unattended runs: SolaX data + pure planning tools, delegation,
# memory. The specialists' MCP tools are listed so a spawned weather-cast/trader
# keeps them even if the cap is applied to children; the dispatcher itself is
# still denied those by its agent policy. set_battery_self_use_mode is never included.
TOOLS="solax-cloud__get_realtime_data,solax-cloud__estimate_grid_charge_need,solax-cloud__build_tou_settings,netatmo-weather__*,rce-prices__*,sessions_spawn,sessions_yield,subagents,read,write,memory_search,memory_get"
existing="$(oc automations list 2>/dev/null || true)"

targets=()
[[ -n "${DISCORD_REPORT_CHANNEL_ID:-}" && -n "${DISCORD_DISPATCHER_BOT_TOKEN:-}" ]] && \
  targets+=("discord|channel:${DISCORD_REPORT_CHANNEL_ID}|--account dispatcher")
[[ "${WHATSAPP_ENABLED:-false}" == "true" && -n "${WHATSAPP_REPORT_TO:-}" ]] && \
  targets+=("whatsapp|${WHATSAPP_REPORT_TO}|")
if [[ ${#targets[@]} -eq 0 ]]; then
  echo "No report channel configured (DISCORD_REPORT_CHANNEL_ID or WHATSAPP_REPORT_TO)." >&2
  exit 1
fi

create() {  # name schedule prompt channel to extra
  local name="$1" schedule="$2" prompt="$3" channel="$4" to="$5" extra="$6"
  if grep -q "$name" <<<"$existing"; then echo "exists: $name"; return; fi
  # shellcheck disable=SC2086
  oc automations create "$schedule" "$prompt" \
    --name "$name" --agent dispatcher --tz "$TZ_NAME" --session isolated \
    --tools "$TOOLS" --announce --channel "$channel" --to "$to" $extra
  echo "created: $name"
}

for target in "${targets[@]}"; do
  IFS='|' read -r channel to extra <<<"$target"
  create "Morning energy report ($channel)" "${MORNING_REPORT_CRON:-0 7 * * *}" \
    "MORNING_REPORT: prepare the morning report as described in AGENTS.md." "$channel" "$to" "$extra"
  create "Evening energy report ($channel)" "${EVENING_REPORT_CRON:-30 21 * * *}" \
    "EVENING_REPORT: prepare the evening report as described in AGENTS.md." "$channel" "$to" "$extra"
done
echo "Run once now to test:  docker compose exec openclaw openclaw automations run <job-id>"
