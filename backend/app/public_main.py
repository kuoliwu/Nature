"""對外公開用的伺服器：只有屋主 / 受託人簽名頁，沒有任何管理 API，也不提供 /docs。

run.py 會把它綁在 127.0.0.1:8001，Cloudflare Tunnel 只轉發到這個 port，
所以即使對外網址外流，外部也碰不到 /init-db、/authorizations 等管理功能。
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.config import settings
from app.main import lifespan
from app.routers import authorizations

app = FastAPI(
    title=f"{settings.app_name}（公開頁面）",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(authorizations.public)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home():
    # 只用來確認對外網址可以連線；不透露任何資料
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{settings.app_name}</title></head>"
        '<body style="font-family:sans-serif;text-align:center;padding:48px 16px">'
        f"<h2>{settings.app_name}</h2><p>✅ 連線正常。請使用您收到的專屬連結開啟簽名頁面。</p>"
        "</body></html>"
    )
