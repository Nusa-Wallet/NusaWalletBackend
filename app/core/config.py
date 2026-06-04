from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./nusawallet.db"
    jwt_secret: str = "change-this-in-production-please"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    ai_service_url: str = "http://localhost:8001"

    # Currencies supported in the MVP demo (proposal scope: SGD <-> IDR, plus extras shown in UI)
    supported_currencies: list[str] = ["IDR", "USD", "SGD", "EUR", "MYR"]
    base_currency: str = "IDR"


settings = Settings()
