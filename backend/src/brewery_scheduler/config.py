from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://brewery:brewery@localhost:5432/brewery"
    api_title: str = "Brewery Scheduler API"

    # Greift nur ohne Caddy davor (Entwicklung): das Protokoll soll dann
    # sichtbar unbestimmt bleiben statt jemanden fälschlich zu nennen.
    fallback_benutzer: str = "unbekannt"


settings = Settings()
