from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Copiloto Pedagógico Inteligente DIFODS"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 7001
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./copilot.db"
    db_name: str = "diplomado"
    db_user: str = "postgres"
    db_password: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "amqp://guest:guest@localhost:5672//"
    moodle_webhook_secret: str = "development-only-secret"
    moodle_base_url: str = ""
    moodle_token: str = ""
    moodle_service_path: str = "/webservice/rest/server.php"
    moodle_timeout_seconds: int = 120
    moodle_course_id: int | None = None
    moodle_cm_id: int | None = None
    moodle_include_names: bool = False
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-05-01-preview"
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = "gpt-4o"
    ai_analysis_enabled: bool = True
    ai_auto_analysis_enabled: bool = False
    ai_max_file_mb: int = 20
    ai_max_video_mb: int = 500
    ai_max_chars_per_file: int = 18000
    ai_video_sample_frames: int = 6
    ai_request_timeout_seconds: int = 120
    cors_origins: list[str] | str = ["http://localhost:3000", "http://127.0.0.1:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("moodle_course_id", "moodle_cm_id", mode="before")
    @classmethod
    def blank_id_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def build_database_url(self) -> "Settings":
        if not self.database_url:
            user = quote_plus(self.db_user)
            password = quote_plus(self.db_password)
            credentials = f"{user}:{password}" if password else user
            self.database_url = (
                f"postgresql+psycopg://{credentials}@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
