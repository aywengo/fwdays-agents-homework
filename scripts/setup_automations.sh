#!/usr/bin/env bash
# Create the scheduled automations (idempotent: existing jobs are kept by name).
# Usage: scripts/setup_automations.sh            (create missing jobs)
#        scripts/setup_automations.sh --list     (show jobs)
#
# Jobs:
#   dispatcher    Morning / Evening energy report      -> every report channel
#   weather-cast  Weather alert check (every 3 h)       -> every report channel, silent (NO_REPLY) when nothing new
#   all agents    Monthly memory maintenance            -> no delivery
# Every job runs in an isolated session with an explicit read-mostly tool cap;
# battery control (set_battery_self_use_mode) is never included.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; . ./.env; set +a
oc() { docker compose exec -T openclaw openclaw "$@"; }

if [[ "${1:-}" == "--list" ]]; then oc automations list; exit 0; fi

TZ_NAME="${HOME_TZ:-Europe/Warsaw}"
# Reports: SolaX data + pure planning tools, delegation, memory. The specialists'
# MCP tools are listed so a spawned weather-cast/trader keeps them even if the cap
# is applied to children; the dispatcher itself is still denied those by its policy.
REPORT_TOOLS="solax-cloud__get_realtime_data,solax-cloud__estimate_grid_charge_need,solax-cloud__build_tou_settings,netatmo-weather__*,rce-prices__*,sessions_spawn,sessions_yield,subagents,read,write,memory_search,memory_get"
ALERT_TOOLS="netatmo-weather__*,read,write,memory_search,memory_get"
MAINTENANCE_TOOLS="read,write,memory_search,memory_get"
existing="$(oc automations list 2>/dev/null || true)"

# channel|to|discord-account-for-dispatcher|discord-account-for-weather-cast
targets=()
if [[ -n "${DISCORD_REPORT_CHANNEL_ID:-}" && -n "${DISCORD_DISPATCHER_BOT_TOKEN:-}" ]]; then
  weather_account=dispatcher
  [[ -n "${DISCORD_WEATHER_BOT_TOKEN:-}" ]] && weather_account=weather-cast
  targets+=("discord|channel:${DISCORD_REPORT_CHANNEL_ID}|dispatcher|${weather_account}")
fi
[[ "${WHATSAPP_ENABLED:-false}" == "true" && -n "${WHATSAPP_REPORT_TO:-}" ]] && \
  targets+=("whatsapp|${WHATSAPP_REPORT_TO}||")
if [[ ${#targets[@]} -eq 0 ]]; then
  echo "No report channel configured (DISCORD_REPORT_CHANNEL_ID or WHATSAPP_REPORT_TO)." >&2
  exit 1
fi

exists() { grep -qF "$1" <<<"$existing" && echo "exists: $1"; }

announce() {  # name agent schedule tools prompt channel to account
  local name="$1" agent="$2" schedule="$3" tools="$4" prompt="$5" channel="$6" to="$7" account="$8"
  exists "$name" && return
  local extra=()
  [[ -n "$account" ]] && extra=(--account "$account")
  # ${extra[@]+...}: macOS bash 3.2 treats an empty array as unbound under set -u
  oc automations create "$schedule" "$prompt" \
    --name "$name" --agent "$agent" --tz "$TZ_NAME" --session isolated \
    --tools "$tools" --announce --channel "$channel" --to "$to" ${extra[@]+"${extra[@]}"}
  echo "created: $name"
}

silent() {  # name agent schedule tools prompt
  local name="$1" agent="$2" schedule="$3" tools="$4" prompt="$5"
  exists "$name" && return
  oc automations create "$schedule" "$prompt" \
    --name "$name" --agent "$agent" --tz "$TZ_NAME" --session isolated \
    --tools "$tools" --no-deliver
  echo "created: $name"
}

# OpenClaw delivers each job to one channel, so report and alert jobs exist per
# channel. The prompt names the channel; agents keep memory writes idempotent
# (one snapshot per day and kind) and de-duplicate alerts per channel.
for target in "${targets[@]}"; do
  IFS='|' read -r channel to dispatcher_account weather_account <<<"$target"
  announce "Morning energy report ($channel)" dispatcher "${MORNING_REPORT_CRON:-0 7 * * *}" "$REPORT_TOOLS" \
    "MORNING_REPORT (channel: $channel): prepare the morning report as described in AGENTS.md." \
    "$channel" "$to" "$dispatcher_account"
  announce "Evening energy report ($channel)" dispatcher "${EVENING_REPORT_CRON:-30 21 * * *}" "$REPORT_TOOLS" \
    "EVENING_REPORT (channel: $channel): prepare the evening report as described in AGENTS.md." \
    "$channel" "$to" "$dispatcher_account"
  announce "Weather alert check ($channel)" weather-cast "${WEATHER_ALERT_CRON:-15 6-21/3 * * *}" "$ALERT_TOOLS" \
    "WEATHER_ALERT_CHECK (channel: $channel): run the scheduled check from the weather-alerts skill. Reply NO_REPLY when there is no new or escalated alert for this channel." \
    "$channel" "$to" "$weather_account"
done

for agent in dispatcher weather-cast trader; do
  silent "Memory maintenance ($agent)" "$agent" "${MEMORY_MAINTENANCE_CRON:-30 3 1 * *}" "$MAINTENANCE_TOOLS" \
    "MEMORY_MAINTENANCE: run the monthly maintenance from the memory-hygiene skill."
done

echo "Run once now to test:  docker compose exec openclaw openclaw automations run <job-id>"
