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

新環境（新電腦、重新下載程式）請先在專案根目錄執行一次 ./install.sh（= python3 backend/run.py --install）。

不需要先 source .venv/bin/activate：用任何 Python 執行，都會自動改用 run.py 旁邊的 .venv
（程式放在哪個資料夾都可以，例如 python3 /任意路徑/backend/run.py）。

啟動前自動檢查環境，缺少的會直接補上（新下載的程式第一次執行會比較久）：
  backend/.venv 不存在          → 建立
  requirements.txt 有變動        → pip install（以雜湊值記錄在 .venv/.requirements.sha256）
  backend/.env 不存在            → 由 .env.example 複製（.env.example 就是實際使用的設定）
  backend/webapp 不存在（電腦版）→ 在 mobile 執行 npm ci / npm run build:web（失敗不影響後端）
"""

import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
MOBILE = HERE.parent / "mobile"


def ensure_venv() -> None:
    """建立 .venv、requirements.txt 變動時安裝套件；失敗就停止（不要把套件裝進別的專案的 venv）"""
    if not VENV_PYTHON.exists():
        print(f"  🔧 建立 Python 虛擬環境：{VENV}")
        if subprocess.call([sys.executable, "-m", "venv", str(VENV)]) != 0 or not VENV_PYTHON.exists():
            shutil.rmtree(VENV, ignore_errors=True)  # 建一半的 venv 會讓下次以為已經建好
            print("  ❌ 無法建立虛擬環境。Ubuntu 請先執行：sudo apt install python3-venv，再重新執行 python run.py")
            raise SystemExit(1)
    requirements = HERE / "requirements.txt"
    stamp = VENV / ".requirements.sha256"
    digest = hashlib.sha256(requirements.read_bytes()).hexdigest()
    if stamp.exists() and stamp.read_text().strip() == digest:
        return
    print("  🔧 安裝 / 更新 Python 套件（requirements.txt）…")
    pip = [str(VENV_PYTHON), "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", str(requirements)]
    if subprocess.call(pip) != 0:
        print(f"  ❌ 套件安裝失敗（見上方訊息）。修正後重新執行 python run.py，或手動執行：{' '.join(pip)}")
        raise SystemExit(1)
    stamp.write_text(digest + "\n")
    print("  ✅ Python 套件已安裝")


def ensure_env_file() -> None:
    env, example = HERE / ".env", HERE / ".env.example"
    if env.exists() or not example.exists():
        return
    shutil.copyfile(example, env)
    print(f"  🔧 已建立 {env}（由 .env.example 複製）")


def find_npm() -> str | None:
    """WSL 的 PATH 可能先找到 Windows 版 npm（/mnt/c/...），在 Linux 檔案上執行會出錯 → 改找 nvm 安裝的"""
    npm = shutil.which("npm")
    if npm and not npm.startswith("/mnt/"):
        return npm
    candidates = sorted(glob.glob(str(Path.home() / ".nvm/versions/node/*/bin/npm")), key=_node_version)
    return candidates[-1] if candidates else None


def _node_version(npm: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", Path(npm).parent.parent.name))


def ensure_webapp() -> None:
    """電腦版 / 手機網頁版（/app）還沒建置時自動建置；失敗只提示，後端照常啟動"""
    if (HERE / "webapp" / "index.html").exists() or not (MOBILE / "package.json").exists():
        return
    npm = find_npm()
    if npm is None:
        print("  ⚠️ 找不到 Node.js（npm），略過建置電腦版。安裝 Node.js 後在 mobile 資料夾執行 npm run build:web")
        return
    env = {**os.environ, "PATH": f"{Path(npm).parent}{os.pathsep}{os.environ.get('PATH', '')}", "CI": "1"}
    steps = [] if (MOBILE / "node_modules").is_dir() else [[npm, "ci"]]
    steps.append([npm, "run", "build:web"])
    print("  🔧 建置電腦版 / 手機網頁版（/app），第一次約需 1～3 分鐘…")
    for step in steps:
        if subprocess.call(step, cwd=MOBILE, env=env) != 0:
            print(f"  ⚠️ 執行 {' '.join(step[1:])} 失敗，略過電腦版（後端照常啟動）。可稍後在 mobile 資料夾手動執行 npm run build:web")
            return
    print("  ✅ 電腦版建置完成")


def prepare_environment() -> None:
    if os.environ.get("RUN_PY_REEXEC"):  # 外層已檢查過
        return
    sys.stdout.reconfigure(line_buffering=True)  # 輸出導向檔案時，訊息與 pip / npm 的輸出順序才不會錯亂
    ensure_venv()
    ensure_env_file()
    ensure_webapp()


def use_project_venv() -> None:
    """目前不是用 backend/.venv 的 Python 執行時，改用它重新執行本程式（參數照傳）"""
    if Path(sys.prefix).resolve() == VENV.resolve() or os.environ.get("RUN_PY_REEXEC"):
        return
    args = [str(VENV_PYTHON), str(HERE / "run.py"), *sys.argv[1:]]
    env = {**os.environ, "RUN_PY_REEXEC": "1"}  # 避免設定異常時無限重新執行
    sys.stdout.flush()  # exec 會丟掉還沒輸出的訊息
    if os.name == "nt":  # Windows 沒有真正的 exec
        sys.exit(subprocess.call(args, env=env))
    os.execve(args[0], args, env)


if __name__ == "__main__":
    prepare_environment()
    if "--install" in sys.argv:  # install.sh：只準備環境，不啟動
        print("  ✅ 環境已就緒，執行 python3 backend/run.py 啟動")
        sys.exit(0)
    use_project_venv()

import argparse  # noqa: E402
import asyncio  # noqa: E402
import contextlib  # noqa: E402
import json  # noqa: E402
import socket  # noqa: E402

import uvicorn  # noqa: E402

from app.config import settings  # noqa: E402

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


async def keep_admin_funnel(port: int, target: int) -> None:
    """Funnel 設定偶爾會被 Tailscale 重設（例如 Windows 上的 Tailscale 重新啟動）→ 每分鐘檢查，不見了就補回"""
    cli = tailscale_cli()
    while cli:
        await asyncio.sleep(60)
        try:
            if await asyncio.to_thread(_funnel_url, cli, port, target):
                continue
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            continue  # Tailscale 暫時沒回應，下一輪再試
        url = await asyncio.to_thread(ensure_admin_funnel, port, target)
        print(f"  🔁 Tailscale Funnel 設定不見了，已重新開啟：{url}/app" if url else "  ⚠️ Tailscale Funnel 設定不見了，重新開啟失敗（下一分鐘再試）")


async def serve_all(servers: list[uvicorn.Server], tunnel: bool, funnel_port: int | None = None) -> None:
    tasks = [asyncio.create_task(run_tunnel())] if tunnel else []
    if funnel_port:
        tasks.append(asyncio.create_task(keep_admin_funnel(funnel_port, settings.port)))
    try:
        await asyncio.gather(*(s.serve() for s in servers))
    finally:
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def tailscale_cli() -> str | None:
    """Linux 版 tailscale，或 WSL 裡呼叫 Windows 的 tailscale.exe"""
    for candidate in (shutil.which("tailscale"), "/mnt/c/Program Files/Tailscale/tailscale.exe", shutil.which("tailscale.exe")):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def _funnel_url(cli: str, port: int, target: int) -> str | None:
    """目前的 Funnel 設定裡，已把 https 的 port 轉到本機 target 時回傳對外網址"""
    out = subprocess.run([cli, "funnel", "status", "--json"], capture_output=True, text=True, timeout=20).stdout
    status = json.loads(out or "{}")
    for host_port, web in (status.get("Web") or {}).items():
        proxy = ((web.get("Handlers") or {}).get("/") or {}).get("Proxy", "")
        if host_port.endswith(f":{port}") and (status.get("AllowFunnel") or {}).get(host_port) and proxy.endswith(f":{target}"):
            host = host_port.rsplit(":", 1)[0]
            return f"https://{host}" if port == 443 else f"https://{host}:{port}"
    return None


def ensure_admin_funnel(port: int, target: int) -> str | None:
    """確保 Tailscale Funnel 把管理 APP 開放到外網（設定會保留在 Tailscale，重開機也有效）；回傳網址"""
    cli = tailscale_cli()
    if cli is None:
        print("  ⚠️ 找不到 tailscale，管理 APP 只能在區網使用（外網使用請安裝 Tailscale，見 README 第 6 節）")
        return None
    try:
        url = _funnel_url(cli, port, target)
        if url:
            return url
        result = subprocess.run(
            [cli, "funnel", "--bg", f"--https={port}", f"http://127.0.0.1:{target}"],
            capture_output=True, text=True, timeout=60,
        )
        url = _funnel_url(cli, port, target)
        if url is None:
            message = (result.stderr or result.stdout).strip().splitlines()
            print(f"  ⚠️ 無法開啟 Tailscale Funnel（port {port}）：{message[-1] if message else '未知錯誤'}")
        return url
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
        print(f"  ⚠️ 無法開啟 Tailscale Funnel：{e}")
        return None


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
    if (Path(__file__).parent / "webapp").is_dir():
        print(f"  電腦版（瀏覽器）    ：http://localhost:{port}/app")
    print(f"  手機 APP（Wi-Fi）   ：http://{source_ip('8.8.8.8') or '127.0.0.1'}:{port}")
    ts = tailscale_ip()
    print(f"  手機 APP（Tailscale）：http://{ts}:{port}" if ts else "  手機 APP（Tailscale）：未偵測到 Tailscale")
    funnel = None
    if settings.admin_funnel_port:
        funnel = ensure_admin_funnel(settings.admin_funnel_port, port)
        if funnel:
            print(f"  手機 APP（任何網路）：{funnel}/app　← 手機不需安裝 Tailscale，Wi-Fi / 5G 都可用")
            if not (Path(__file__).parent / "webapp").is_dir():
                print("     （尚未建置網頁版：請在 mobile 資料夾執行 npm run build:web）")
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
        asyncio.run(serve_all(servers, args.tunnel, settings.admin_funnel_port if funnel else None))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
