"""啟動本地伺服器並印出手機 APP 應輸入的 IP。

用法：
    python run.py            # 只啟動後端（區網 / Tailscale 使用）
    python run.py --tunnel   # 後端 + Cloudflare 通道（外部的人可開啟簽名頁），Ctrl+C 一起關閉

同時啟動兩個伺服器：
  0.0.0.0:8000    管理 API + 公開頁面（區網 / Tailscale 使用）
  127.0.0.1:8001  只有公開頁面（通道只轉發到這裡）

通道模式：
  .env 有 CLOUDFLARE_TUNNEL_TOKEN → 具名通道，固定網址（PUBLIC_BASE_URL）
  沒有                           → 快速通道，每次啟動網址都不同
"""

import argparse
import asyncio
import contextlib
import re
import shutil
import socket
from pathlib import Path

import uvicorn

from app.config import settings

QUICK_TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def source_ip(target: str) -> str | None:
    # 不會真的送出封包，只是讓 OS 選出連到 target 時會用的網卡 IP
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect((target, 80))
            return s.getsockname()[0]
        except OSError:
            return None


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # 與 uvicorn 相同設定：剛關閉、還在 TIME_WAIT 的連線不算占用，只有真的有人在 listen 才算
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
            return False
        except OSError:
            return True


def tailscale_ip() -> str | None:
    # 100.100.100.100 是 Tailscale 內部 DNS，有連上 Tailscale 時會走 100.x 網卡
    ip = source_ip("100.100.100.100")
    return ip if ip and ip.startswith("100.") else None


def find_cloudflared() -> str | None:
    # VS Code 的 WSL 終端機不會讀 ~/.profile，~/.local/bin 可能不在 PATH 裡
    local = Path.home() / ".local" / "bin" / "cloudflared"
    return shutil.which("cloudflared") or (str(local) if local.is_file() else None)


async def run_tunnel() -> None:
    exe = find_cloudflared()
    if exe is None:
        print("  ❌ 找不到 cloudflared，請先依 README 第 9 節安裝。後端仍會繼續執行。\n")
        return

    named = bool(settings.cloudflare_tunnel_token)
    if named:
        args = [exe, "tunnel", "--no-autoupdate", "run", "--token", settings.cloudflare_tunnel_token]
    else:
        args = [exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{settings.public_port}"]

    # 獨立的 process group：Ctrl+C 只送給 Python，由我們在後端關閉後再結束通道
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, start_new_session=True
    )
    announced = False
    try:
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            if not announced and not named and (m := QUICK_TUNNEL_URL.search(line)):
                settings.public_url_file.write_text(m.group(0) + "\n", "utf-8")
                print(f"\n  ✅ 對外網址（快速通道，重開會變）：{m.group(0)}")
                print("     產生屋主連結：python -m scripts.owner_link <預約編號>\n")
                announced = True
            elif not announced and named and "Registered tunnel connection" in line:
                print(f"\n  ✅ 對外網址（固定）：{settings.public_base_url or '請在 .env 設定 PUBLIC_BASE_URL'}\n")
                announced = True
            elif " ERR " in line:
                print(f"  [通道] {line}")
        print("  ⚠️ Cloudflare 通道已停止，外部暫時無法開啟簽名頁（後端仍在執行）")
    finally:
        if proc.returncode is None:
            proc.terminate()
            with contextlib.suppress(ProcessLookupError):
                await proc.wait()
        if not named:
            settings.public_url_file.unlink(missing_ok=True)


async def serve_all(servers: list[uvicorn.Server], tunnel: bool) -> None:
    tunnel_task = asyncio.create_task(run_tunnel()) if tunnel else None
    try:
        await asyncio.gather(*(s.serve() for s in servers))
    finally:
        if tunnel_task:
            tunnel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await tunnel_task


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tunnel", action="store_true", help="同時啟動 Cloudflare 通道，讓外部可開啟簽名頁")
    args = parser.parse_args()

    port = settings.port
    busy = [p for h, p in ((settings.host, port), ("127.0.0.1", settings.public_port)) if port_in_use(h, p)]
    if busy:
        ports = "、".join(map(str, busy))
        print(f"\n  ❌ Port {ports} 已被占用，通常是另一個終端機的 run.py 還在執行。")
        print("     請到那個終端機按 Ctrl+C，或執行以下指令找出並結束它：")
        print(f"     ss -ltnp | grep -E ':({'|'.join(map(str, busy))})\\b'    # 找出 pid")
        print("     kill <pid>\n")
        raise SystemExit(1)

    # 上次若異常結束，留下的快速通道網址已失效
    settings.public_url_file.unlink(missing_ok=True)

    print(f"\n  本機 API 文件       ：http://127.0.0.1:{port}/docs")
    print(f"  手機 APP（Wi-Fi）   ：http://{source_ip('8.8.8.8') or '127.0.0.1'}:{port}")
    ts = tailscale_ip()
    print(f"  手機 APP（5G）      ：http://{ts}:{port}" if ts else "  手機 APP（5G）      ：未偵測到 Tailscale")
    if args.tunnel:
        print("  對外公開頁面        ：啟動 Cloudflare 通道中…（約 5～10 秒）")
    elif settings.public_base_url:
        print(f"  對外公開頁面        ：{settings.public_base_url}（固定網址）")
    else:
        print("  對外公開頁面        ：未開啟（要給外部的人使用時改用 python run.py --tunnel）")
    print()

    servers = [
        uvicorn.Server(uvicorn.Config("app.main:app", host=settings.host, port=port)),
        uvicorn.Server(uvicorn.Config("app.public_main:app", host="127.0.0.1", port=settings.public_port)),
    ]
    try:
        asyncio.run(serve_all(servers, args.tunnel))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
