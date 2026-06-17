from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Meta / Facebook
    meta_verify_token: str = "change-me"
    meta_app_secret: str = ""
    graph_api_version: str = "v23.0"

    # Database
    database_url: str = "sqlite:///./vaovao.db"

    # Google Sheets
    google_service_account_file: str = "./service-account.json"

    # Email
    email_provider: str = "smtp"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "VaoVao Leads <leads@example.com>"
    smtp_use_tls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
