"""判斷請求是否來自外網（經 Tailscale Funnel / Cloudflare 等通道轉發），以及取得真正的用戶端 IP。

管理 API 開放到外網後（run.py 的 ADMIN_FUNNEL_PORT），系統金鑰相關功能與 API 文件只允許區網 / Tailscale / 本機使用。
"""

import ipaddress

from fastapi import Request

# 通道轉發時一定會加上的標頭（直接連線不會有）；有任何一個就當作外網
PROXY_HEADERS = ("x-forwarded-for", "forwarded", "x-forwarded-host", "tailscale-funnel-request", "cf-connecting-ip")
TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")

# 外網看不到的路徑（回 404，不透露存在）
LOCAL_ONLY_PATHS = ("/docs", "/redoc", "/openapi.json", "/init-db", "/db/status", "/auth/setup")


def _peer_ip(request: Request) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(request.client.host) if request.client else None
    except ValueError:
        return None  # 例如測試用的 "testclient"


def is_external(request: Request) -> bool:
    if any(h in request.headers for h in PROXY_HEADERS):
        return True
    ip = _peer_ip(request)
    if ip is None:
        return False
    return not (ip.is_loopback or ip.is_private or ip in TAILSCALE_NET)


def client_ip(request: Request) -> str | None:
    """本機通道轉發時用 X-Forwarded-For 的第一個位址（只信任本機送來的標頭）"""
    ip = _peer_ip(request)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and (ip is None or ip.is_loopback):
        return forwarded.split(",")[0].strip()
    return str(ip) if ip else None


def is_local_only_path(path: str) -> bool:
    return any(path == p or path.startswith(p + "/") for p in LOCAL_ONLY_PATHS)
