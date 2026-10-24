"""啟動本地伺服器並印出手機 APP 應輸入的 IP。用法：python run.py"""

import socket

import uvicorn

from app.config import settings


def source_ip(target: str) -> str | None:
    # 不會真的送出封包，只是讓 OS 選出連到 target 時會用的網卡 IP
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect((target, 80))
            return s.getsockname()[0]
        except OSError:
            return None


def tailscale_ip() -> str | None:
    # 100.100.100.100 是 Tailscale 內部 DNS，有連上 Tailscale 時會走 100.x 網卡
    ip = source_ip("100.100.100.100")
    return ip if ip and ip.startswith("100.") else None


if __name__ == "__main__":
    port = settings.port
    print(f"\n  本機 API 文件       ：http://127.0.0.1:{port}/docs")
    print(f"  手機 APP（Wi-Fi）   ：http://{source_ip('8.8.8.8') or '127.0.0.1'}:{port}")
    ts = tailscale_ip()
    print(f"  手機 APP（5G）      ：http://{ts}:{port}" if ts else "  手機 APP（5G）      ：未偵測到 Tailscale")
    print()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
