import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # 測試時用 APP_ENV_FILE 指到不存在的檔案，避免讀到真正的 .env（例如 SMTP 設定）
        env_file=os.environ.get("APP_ENV_FILE", BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "驗屋與健檢預約管理系統"
    host: str = "0.0.0.0"
    port: int = 8000
    # 只含公開頁面的伺服器，綁 127.0.0.1，給 Cloudflare Tunnel 轉發用
    public_port: int = 8001

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'inspection.db').as_posix()}"
    storage_dir: Path = BASE_DIR / "storage"

    admin_init_key: str = "change-me"

    # 管理者登入；JWT_SECRET 留空時自動產生並存在 data/.jwt_secret
    jwt_secret: str = ""
    jwt_secret_file: Path = BASE_DIR / "data" / ".jwt_secret"
    token_expire_days: int = 30
    id_hash_salt: str = "change-me-too"

    # 業務規則預設值
    default_slot_minutes: int = 30
    default_slot_capacity: int = 3
    report_max_bytes: int = 30 * 1024 * 1024

    # 線上授權
    public_base_url: str | None = None
    # Cloudflare 具名通道的 token（固定網址用）；留空時 run.py --tunnel 使用快速通道
    cloudflare_tunnel_token: str = ""
    # python run.py --tunnel（快速通道）會把臨時對外網址寫在這裡
    public_url_file: Path = BASE_DIR / "data" / "public_url.txt"
    invite_expire_days: int = 7
    owner_link_expire_days: int = 30
    pdf_font_path: Path | None = None

    # Email；smtp_host 為空時改存到 storage/outbox
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
