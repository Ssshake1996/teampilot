from sqlalchemy.engine import URL

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str | None = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "project_mgmt"
    JWT_SECRET_KEY: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 90
    AI_ENCRYPTION_KEY: str = "changeme"
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_FULL_NAME: str = "System Administrator"
    SEED_DEMO_USERS: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def database_url(self) -> str | URL:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return URL.create(
            "postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )


settings = Settings()
