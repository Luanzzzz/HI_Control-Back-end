"""
Configurações da aplicação usando Pydantic Settings
"""
import json
from typing import Any, List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    """
    Configurações centralizadas da aplicação Hi-Control.
    Usa Pydantic Settings para validação e carregamento de variáveis.
    """

    # API
    PROJECT_NAME: str = "Hi-Control API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"

    # Supabase
    SUPABASE_URL: str = Field(..., description="URL do projeto Supabase")
    SUPABASE_KEY: str = Field(..., description="Anon key para cliente")
    SUPABASE_SERVICE_KEY: str = Field(
        ..., description="Service role key para operações admin"
    )

    # JWT
    SECRET_KEY: str = Field(..., description="Chave secreta para JWT")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = (
        "http://localhost:3000,"
        "http://localhost:3001,"
        "http://localhost:5173,"
        "https://hi-control.vercel.app,"
        "https://site-hi-control.vercel.app"
    )

    # CORS Regex (Permitir qualquer subdomínio vercel.app)
    CORS_ORIGIN_REGEX: str = r"https://.*\.vercel\.app"

    # NFS-e (APIs Municipais)
    NFSE_AMBIENTE: str = "producao"  # "producao" ou "homologacao"
    NFSE_TIMEOUT: int = 60  # Timeout em segundos para APIs municipais

    # Google OAuth (para Google Drive)
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None

    # PostgreSQL (futuro - sistema híbrido)
    POSTGRES_URL: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None

    @property
    def cors_origins_list(self) -> List[str]:
        return self._parse_cors_origins(self.CORS_ORIGINS)

    @staticmethod
    def _parse_cors_origins(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if value is None:
            return []

        raw = str(value).strip()
        if not raw:
            return []

        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
            except (ValueError, TypeError, json.JSONDecodeError):
                pass

        return [origin.strip() for origin in raw.split(",") if origin.strip()]

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
    @lru_cache garante que as settings sejam carregadas apenas uma vez.
    """
    s = Settings()
    if not s.GOOGLE_CLIENT_ID or not s.GOOGLE_REDIRECT_URI:
        import warnings
        warnings.warn(
            "Google OAuth não configurado. Drive retornará 503.",
            UserWarning,
            stacklevel=1,
        )
    return s


settings = get_settings()
