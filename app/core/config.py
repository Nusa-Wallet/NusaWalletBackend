from typing import ClassVar

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DEFAULT_JWT_SECRET: ClassVar[str] = "change-this-in-production-please"

    app_env: str = "development"
    database_url: str = "sqlite:///./nusawallet.db"
    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    ai_service_url: str = "http://localhost:8001"
    cors_allow_origins: str = "http://localhost:8081,http://localhost:19006,http://localhost:19000"
    auto_create_tables: bool = True

    # Currencies supported in the MVP demo (proposal scope: SGD <-> IDR, plus extras shown in UI)
    supported_currencies: list[str] = ["IDR", "USD", "SGD", "EUR", "MYR"]
    base_currency: str = "IDR"

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_deploy_settings(self):
        if not self.is_production:
            return self
        if self.jwt_secret == self.DEFAULT_JWT_SECRET:
            raise ValueError("JWT_SECRET must be changed when APP_ENV=production")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ALLOW_ORIGINS cannot include '*' when APP_ENV=production")
        if self.auto_create_tables:
            raise ValueError("AUTO_CREATE_TABLES must be false when APP_ENV=production")
        return self


settings = Settings()
