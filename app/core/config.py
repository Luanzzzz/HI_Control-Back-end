"""
Configurações da aplicação usando Pydantic Settings
"""
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from functools import lru_cache
import os
import logging

logger = logging.getLogger(__name__)


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
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "https://hi-control.vercel.app",
        "https://site-hi-control.vercel.app"
    ]

    # CORS Regex - REMOVIDO wildcard *.vercel.app por segurança
    # Use CORS_ORIGINS para adicionar domínios específicos
    CORS_ORIGIN_REGEX: Optional[str] = None  # ✅ Desabilitado - apenas origens explícitas

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

    # Criptografia de certificados
    CERTIFICATE_ENCRYPTION_KEY: Optional[str] = Field(
        None, description="Chave Fernet para criptografia de certificados A1"
    )

    # SEFAZ (NF-e, NFC-e, CT-e)
    SEFAZ_AMBIENTE: str = Field(
        default="homologacao",
        description="Ambiente SEFAZ: producao | homologacao"
    )
    ALLOW_PRODUCTION_EMISSION: bool = Field(
        default=False,
        description="Permitir emissão de NF-e em produção (proteção contra emissão acidental)"
    )

    # NFS-e Nacional - SEFIN (Emissão)
    NFSE_SEFIN_URL_PRODUCAO: str = "https://sefin.nfse.gov.br/SefinNacional"
    NFSE_SEFIN_URL_HOMOLOGACAO: str = "https://sefin.producaorestrita.nfse.gov.br/SefinNacional"

    # NFS-e Nacional - ADN (Distribuição/Consulta)
    NFSE_ADN_URL_PRODUCAO: str = "https://adn.nfse.gov.br/contribuintes"
    NFSE_ADN_URL_HOMOLOGACAO: str = "https://adn.producaorestrita.nfse.gov.br/contribuintes"

    # Flag de compatibilidade
    USE_MUNICIPAL_LEGACY: bool = Field(
        default=False,
        description="Usar APIs municipais legadas (ABRASF 2.04) em vez da API Nacional"
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins de string ou lista"""
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                import json
                try:
                    return json.loads(v)
                except (ValueError, TypeError):
                    pass
            return [origin.strip() for origin in v.split(",")]
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


def validate_production_security(s: Settings) -> None:
    """
    Valida configurações de segurança em ambiente de produção.
    Bloqueia startup se configurações inseguras forem detectadas.
    """
    if s.ENVIRONMENT != "production":
        return  # Validação apenas em produção

    errors = []

    # =========================================================================
    # VALIDAÇÃO 1: SECRET_KEY não pode conter valores padrão/inseguros
    # =========================================================================
    insecure_patterns = [
        "change", "default", "example", "test", "dev", "demo",
        "gerar-com", "sua-chave", "your-secret", "placeholder"
    ]

    secret_lower = s.SECRET_KEY.lower()
    if any(pattern in secret_lower for pattern in insecure_patterns):
        errors.append(
            "❌ SECRET_KEY contém valor padrão/inseguro. "
            "Gere uma chave única com: openssl rand -hex 32"
        )

    if len(s.SECRET_KEY) < 32:
        errors.append(
            f"❌ SECRET_KEY muito curta ({len(s.SECRET_KEY)} caracteres). "
            "Mínimo recomendado: 32 caracteres."
        )

    # =========================================================================
    # VALIDAÇÃO 2: CERTIFICATE_ENCRYPTION_KEY obrigatória e única
    # =========================================================================
    if not s.CERTIFICATE_ENCRYPTION_KEY:
        errors.append(
            "❌ CERTIFICATE_ENCRYPTION_KEY não configurada. "
            "Gere com: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    elif any(pattern in s.CERTIFICATE_ENCRYPTION_KEY.lower() for pattern in insecure_patterns):
        errors.append(
            "❌ CERTIFICATE_ENCRYPTION_KEY contém valor padrão/inseguro. "
            "Gere uma chave única."
        )

    # =========================================================================
    # VALIDAÇÃO 3: SUPABASE_SERVICE_KEY obrigatória
    # =========================================================================
    if not s.SUPABASE_SERVICE_KEY:
        errors.append("❌ SUPABASE_SERVICE_KEY não configurada.")

    if "sua-service-key" in s.SUPABASE_SERVICE_KEY.lower():
        errors.append(
            "❌ SUPABASE_SERVICE_KEY contém valor placeholder. "
            "Configure com chave real do Supabase."
        )

    # =========================================================================
    # VALIDAÇÃO 4: DISABLE_MODULE_CHECK proibido em produção
    # =========================================================================
    disable_check = os.getenv("DISABLE_MODULE_CHECK", "false").lower()
    if disable_check == "true":
        errors.append(
            "❌ DISABLE_MODULE_CHECK=true é PROIBIDO em produção. "
            "Configure DISABLE_MODULE_CHECK=false ou remova a variável."
        )

    # =========================================================================
    # VALIDAÇÃO 5: Proteção de emissão em produção
    # =========================================================================
    if s.SEFAZ_AMBIENTE == "producao" and not s.ALLOW_PRODUCTION_EMISSION:
        logger.warning(
            "⚠️ SEFAZ_AMBIENTE=producao mas ALLOW_PRODUCTION_EMISSION=false. "
            "Emissão de NF-e está BLOQUEADA. "
            "Para habilitar, configure ALLOW_PRODUCTION_EMISSION=true"
        )

    # =========================================================================
    # VALIDAÇÃO 6: DEBUG deve ser false em produção
    # =========================================================================
    debug_env = os.getenv("DEBUG", "false").lower()
    if debug_env == "true":
        errors.append(
            "❌ DEBUG=true em produção é inseguro. "
            "Configure DEBUG=false."
        )

    # =========================================================================
    # LANÇAR ERRO SE HOUVER PROBLEMAS DE SEGURANÇA
    # =========================================================================
    if errors:
        error_msg = "\n\n" + "=" * 80 + "\n"
        error_msg += "🔴 ERRO DE SEGURANÇA - STARTUP BLOQUEADO\n"
        error_msg += "=" * 80 + "\n\n"
        error_msg += "O sistema detectou configurações inseguras em PRODUÇÃO:\n\n"
        error_msg += "\n".join(f"  {err}" for err in errors)
        error_msg += "\n\n"
        error_msg += "=" * 80 + "\n"
        error_msg += "AÇÕES NECESSÁRIAS:\n"
        error_msg += "=" * 80 + "\n"
        error_msg += "1. Rotacionar credenciais sensíveis (ver SECURITY_ROTATION.md)\n"
        error_msg += "2. Configurar variáveis como SECRETS do hosting (não arquivo .env)\n"
        error_msg += "3. Executar checklist de segurança pré-deploy\n"
        error_msg += "=" * 80 + "\n\n"

        raise RuntimeError(error_msg)


def log_startup_info(s: Settings) -> None:
    """
    Loga informações de configuração no startup (sem expor valores sensíveis).
    """
    logger.info("=" * 60)
    logger.info("HI-CONTROL API - CONFIGURAÇÃO DE STARTUP")
    logger.info("=" * 60)
    logger.info(f"Ambiente: {s.ENVIRONMENT}")
    logger.info(f"SEFAZ Ambiente: {s.SEFAZ_AMBIENTE}")
    logger.info(f"Emissão Produção Permitida: {s.ALLOW_PRODUCTION_EMISSION}")
    logger.info(f"Supabase URL: {s.SUPABASE_URL}")
    logger.info(f"Google OAuth Configurado: {bool(s.GOOGLE_CLIENT_ID)}")
    logger.info(f"Certificado Encryption Configurado: {bool(s.CERTIFICATE_ENCRYPTION_KEY)}")

    # ⚠️ NUNCA logar valores de chaves/secrets
    logger.info("=" * 60)

    # Warnings para configurações faltantes (não críticas)
    if not s.GOOGLE_CLIENT_ID or not s.GOOGLE_REDIRECT_URI:
        logger.warning("⚠️ Google OAuth não configurado. Drive retornará 503.")

    if s.ENVIRONMENT == "production" and s.SEFAZ_AMBIENTE == "homologacao":
        logger.warning(
            "⚠️ ENVIRONMENT=production mas SEFAZ_AMBIENTE=homologacao. "
            "Verifique se isso é intencional."
        )


@lru_cache()
def get_settings() -> Settings:
    """
    Retorna instância singleton das configurações.
    @lru_cache garante que as settings sejam carregadas apenas uma vez.
    """
    s = Settings()

    # Validar segurança em produção
    validate_production_security(s)

    # Logar informações de startup (sem expor segredos)
    log_startup_info(s)

    return s


settings = get_settings()
