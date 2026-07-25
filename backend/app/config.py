from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://billsplitter:billsplitter@localhost:5433/billsplitter"

    anthropic_api_key: str = ""
    extraction_model: str = "claude-haiku-4-5"
    # Transcription is a perception task, not a reasoning one. Deep thinking
    # here mostly buys output tokens, so the default is the cheapest rung.
    extraction_effort: str = "low"
    # Digitally generated PDFs carry a text layer. Reading it locally avoids
    # sending page images to the model, which is where the cost actually is.
    prefer_pdf_text_layer: bool = True

    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 15

    cors_origins: str = "http://localhost:5173"

    # US locale is fixed for v1 — see REQUIREMENTS.md section 8.
    currency: str = "USD"
    timezone: str = "America/New_York"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def extraction_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
