#!/usr/bin/env bash
set -uo pipefail

: "${DB_NAME:?}" "${MONGO_BACKUP_PASSWORD:?}" "${RESTIC_PASSWORD:?}" "${RESTIC_REPOSITORY:?}"
interval=${BACKUP_INTERVAL_SECONDS:-3600}
remote=${RESTIC_REMOTE_REPOSITORY:-}
remote_configured=$([ -n "$remote" ] && echo true || echo false)
uri="mongodb://snp_backup:${MONGO_BACKUP_PASSWORD}@mongo:27017/?authSource=admin&replicaSet=rs0"
pruned_marker="${RESTIC_REPOSITORY}.pruned"
export RESTIC_FROM_PASSWORD=$RESTIC_PASSWORD

write_status() {
  STATUS_SET="$1" mongosh "$uri" --quiet --eval '
    db.getSiblingDB(process.env.DB_NAME).ops_status.updateOne(
      { _id: "backup" }, { $set: EJSON.parse(process.env.STATUS_SET) }, { upsert: true })' >/dev/null \
    || echo "backup: could not write ops_status" >&2
}

fail() {
  echo "backup: $1" >&2
  write_status "$(jq -nc --arg error "$1" --argjson interval "$interval" --argjson remote "$remote_configured" \
    '{last_error_at: {"$date": (now | todate)}, last_error: $error, interval_seconds: $interval, remote_configured: $remote}')"
  return 1
}

count_patients() {
  mongosh "$uri" --quiet --eval 'db.getSiblingDB(process.env.DB_NAME).patients.countDocuments({})'
}

copy_to_remote() {
  restic -r "$remote" cat config >/dev/null 2>&1 \
    || restic -r "$remote" init --quiet --from-repo "$RESTIC_REPOSITORY" --copy-chunker-params \
    || return 1
  restic -r "$remote" copy --quiet --retry-lock 10m --from-repo "$RESTIC_REPOSITORY"
}

forget() {
  restic forget "$@" --quiet --retry-lock 10m --tag snp --keep-hourly 48 --keep-daily 30 --keep-monthly 12 --prune
}

prune_once_a_day() {
  local today
  today=$(date -u +%F)
  [ "$(cat "$pruned_marker" 2>/dev/null)" = "$today" ] && return 0
  forget || return 1
  if [ -n "$remote" ]; then
    forget -r "$remote" || return 1
  fi
  echo "$today" > "$pruned_marker"
}

run_once() {
  local patients summary now remote_ok=false error=""
  if [ ! -f "$RESTIC_REPOSITORY/config" ]; then
    restic init --quiet || { fail "local repository init failed"; return 1; }
  fi
  patients=$(count_patients) || { fail "MongoDB unreachable or login refused"; return 1; }
  if ! summary=$(restic backup --json --quiet --retry-lock 10m --host snp --tag snp --tag "patients=$patients" \
      --stdin-filename snp.archive.gz --stdin-from-command -- \
      mongodump --uri "$uri" --oplog --gzip --archive --quiet \
    | jq -c 'select(.message_type == "summary")') || [ -z "$summary" ]; then
    fail "dump failed"
    return 1
  fi
  if [ -n "$remote" ]; then
    if copy_to_remote; then remote_ok=true; else error="remote copy failed"; fi
  fi
  prune_once_a_day || error="${error:+$error; }prune failed"
  now=$(date -u +%FT%TZ)
  write_status "$(jq -nc --argjson summary "$summary" --argjson patients "$patients" --argjson interval "$interval" \
      --argjson remote "$remote_configured" --argjson remote_ok "$remote_ok" --arg error "$error" --arg now "$now" '
    {last_success_at: {"$date": $now}, bytes: $summary.total_bytes_processed,
     patients_count: $patients, interval_seconds: $interval, remote_configured: $remote}
    + (if $remote_ok then {remote_last_success_at: {"$date": $now}} else {} end)
    + (if $error != "" then {last_error_at: {"$date": $now}, last_error: $error} else {} end)')"
  [ -z "$error" ]
}

[ -f "$RESTIC_REPOSITORY/config" ] && restic unlock --quiet
while true; do
  run_once
  result=$?
  [ -n "${BACKUP_ONCE:-}" ] && exit "$result"
  sleep "$interval"
done
