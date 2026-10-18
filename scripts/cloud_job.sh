#!/usr/bin/env bash
# Cloud Run Job entry point: judge this month's news and publish judge.json next to the price export.
#   $DATA_MOUNT/partner/chin-2026-10-15/   price contract + archive (read)      -> DATA_DIR
#   $DATA_MOUNT/export/news_feed.csv       live news feed from the caller (read) -> NEWS_FEED
#   $DATA_MOUNT/judge/                     judgments.sqlite3 + article_cache (job state)
#   $DATA_MOUNT/export/judge.json          what the API serves
# SQLite never runs on the mount (gcsfuse has no file locking): copy in, work on local disk, copy back.
# Without DATA_MOUNT it runs the daily command against the local .env paths.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
export PYTHONPATH=${PYTHONPATH:-src}
[ -z "${DATA_MOUNT:-}" ] && exec python3 -m hardware_signal.cli daily "$@"
M=$DATA_MOUNT
log() { echo "[judge_job] $*" >&2; }
export DATA_DIR=${DATA_DIR:-$M/partner/chin-2026-10-15}
export NEWS_FEED=${NEWS_FEED:-$M/export/news_feed.csv}
export OUTPUT_DIR=${OUTPUT_DIR:-/tmp/judge}
export DB_PATH=$OUTPUT_DIR/judgments.sqlite3
[ -f "$NEWS_FEED" ] || { log "no $NEWS_FEED; run the caller job first"; exit 1; }
mkdir -p "$OUTPUT_DIR"
[ -d "$M/judge" ] && cp -R "$M/judge/." "$OUTPUT_DIR/"

python3 -m hardware_signal.cli daily --output "$OUTPUT_DIR/judge.json" "$@"; status=$?
log "daily exit $status (0 ok, 3 = published but one category failed)"

if [ -f "$OUTPUT_DIR/judge.json" ] && { [ "$status" -eq 0 ] || [ "$status" -eq 3 ]; }; then
  mkdir -p "$M/export" && cp "$OUTPUT_DIR/judge.json" "$M/export/judge.json" && log "published judge.json"
fi
mkdir -p "$M/judge/article_cache"
[ -f "$DB_PATH" ] && cp "$DB_PATH" "$M/judge/judgments.sqlite3"
[ -d "$OUTPUT_DIR/article_cache" ] && cp -R "$OUTPUT_DIR/article_cache/." "$M/judge/article_cache/"
exit "$status"
