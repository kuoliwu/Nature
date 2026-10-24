#!/usr/bin/env bash
# 啟動 Expo 開發伺服器，讓 QR code 使用正確的 IP
#   npm run wifi   → 手機與電腦同一個 Wi-Fi
#   npm run 5g     → 手機走行動網路，經 Tailscale 連線
set -euo pipefail

mode="${1:-wifi}"

case "$mode" in
  wifi)
    # 連外時使用的網卡 IP（即區網 IP）
    ip=$(ip -4 route get 8.8.8.8 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')
    ;;
  5g)
    ip=$(ip -4 -o addr show | awk '{split($4, a, "/"); if (a[1] ~ /^100\./) {print a[1]; exit}}')
    if [[ -z "$ip" ]]; then
      echo "找不到 Tailscale IP（100.x.x.x）：請確認電腦上的 Tailscale 已登入並連線。" >&2
      exit 1
    fi
    ;;
  *)
    echo "用法：$0 [wifi|5g]" >&2
    exit 1
    ;;
esac

echo
echo "  模式：$mode"
echo "  APP 主機位址請填：$ip:8000"
echo

export REACT_NATIVE_PACKAGER_HOSTNAME="$ip"
exec npx expo start
