from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "驗屋與健檢預約管理系統"
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'inspection.db').as_posix()}"
    storage_dir: Path = BASE_DIR / "storage"

    admin_init_key: str = "change-me"
    id_hash_salt: str = "change-me-too"

    # 業務規則預設值
    default_slot_minutes: int = 30
    default_slot_capacity: int = 3
    report_max_bytes: int = 30 * 1024 * 1024

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
