#!/usr/bin/env bash
# 新環境（新電腦、重新下載程式）執行一次：
#   建立 backend/.venv、安裝 Python 套件、由 .env.example 建立 .env、建置電腦版（/app）
# 之後啟動只要 python3 backend/run.py
set -e
cd "$(dirname "$0")"
exec python3 backend/run.py --install
