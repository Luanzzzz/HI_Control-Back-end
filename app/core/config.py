"""
Configurações da aplicação usando Pydantic Settings
"""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """
    Configurações centralizadas da aplicação Hi-Control.
    Utiliza Pydantic Settings para validação e carregamento de variáveis de ambiente.
    """

    # API
    PROJECT_NAME: str = "Hi-Control API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Supabase
    SUPABASE_URL: str = Field(..., description="URL do projeto Supabase")
    SUPABASE_KEY: str = Field(..., description="Anon key para cliente")
    SUPABASE_SERVICE_KEY: str = Field(..., description="Service role key para operações admin")

    # JWT
    SECRET_KEY: str = Field(..., description="Chave secreta para JWT")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "https://hi-control.vercel.app",
        "https://site-hi-control.vercel.app"
    ]

    # CORS Regex (Permitir qualquer subdomínio vercel.app)
    CORS_ORIGIN_REGEX: str = r"https://.*\.vercel\.app"

    # PostgreSQL (futuro - sistema híbrido)
    POSTGRES_URL: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins de string ou lista"""
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except:
                    pass
            return [origin.strip() for origin in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Retorna instância singleton das configurações.
    O decorator @lru_cache garante que as settings sejam carregadas apenas uma vez.
    """
    return Settings()


settings = get_settings()
