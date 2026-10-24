#!/usr/bin/env bash
# 背景啟動後端（給開機自動啟動用）。輸出寫到 backend/logs/server.log
# 手動使用：bash ~/stock/nature/nature/backend/scripts/start_server.sh
set -uo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs
LOG=logs/server.log

# 超過 10MB 就換檔，保留一份舊的
if [[ -f "$LOG" && $(stat -c %s "$LOG") -gt 10485760 ]]; then
  mv -f "$LOG" "$LOG.1"
fi

{
  echo
  echo "===== $(date '+%F %T') 啟動 ====="
} >> "$LOG"

# 不需要互動式 shell：直接用 venv 裡的 python；PYTHONUNBUFFERED 讓日誌即時寫入
export PYTHONUNBUFFERED=1
exec .venv/bin/python run.py >> "$LOG" 2>&1
