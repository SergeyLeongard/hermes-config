#!/usr/bin/env bash
set -euo pipefail

CRON_FILE="/home/sadmin/.hermes/hermes-agent/cron/jobs.hermes.cron"

if [[ ! -f "$CRON_FILE" ]]; then
  echo "apply_hermes_cron: status=error detail=missing_cron_file path=$CRON_FILE"
  exit 1
fi

crontab "$CRON_FILE"
COUNT="$(crontab -l | wc -l | tr -d ' ')"
echo "apply_hermes_cron: status=ok lines=$COUNT source=$CRON_FILE"
