"""
Configurações do Bot de Busca de Notas

Seguindo padrões MCP: configurações centralizadas e validadas.
"""

import os
from typing import Optional
from dotenv import load_dotenv
from pathlib import Path

# Carregar variáveis de ambiente
load_dotenv()

# Caminho base do bot
BOT_ROOT = Path(__file__).parent


class BotConfig:
    """
    Configurações do bot seguindo padrões MCP.
    
    Centraliza todas as configurações e valida valores críticos.
    """
    
    # ============================================
    # SUPABASE (Resource Pattern MCP)
    # ============================================
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    
    @classmethod
    def validate_supabase(cls) -> bool:
        """Valida configurações do Supabase."""
        if not cls.SUPABASE_URL:
            raise ValueError("SUPABASE_URL não configurada")
        if not cls.SUPABASE_KEY:
            raise ValueError("SUPABASE_KEY não configurada")
        return True
    
    # ============================================
    # BASE NACIONAL NFS-e
    # ============================================
    BASE_NACIONAL_URL_PRODUCAO: str = os.getenv(
        "BASE_NACIONAL_URL",
        "https://sefin.nfse.gov.br/sefinnacional"
    )
    BASE_NACIONAL_URL_HOMOLOGACAO: str = os.getenv(
        "BASE_NACIONAL_URL_HOMOLOGACAO",
        "https://sefin.producaorestrita.nfse.gov.br/sefinnacional"
    )
    BASE_NACIONAL_TIMEOUT: int = int(os.getenv("BASE_NACIONAL_TIMEOUT", "60"))
    BASE_NACIONAL_HOMOLOGACAO: bool = os.getenv("BASE_NACIONAL_HOMOLOGACAO", "false").lower() == "true"
    
    # ============================================
    # AGENDAMENTO (APScheduler)
    # ============================================
    INTERVALO_EXECUCAO_MINUTOS: int = int(os.getenv("BOT_INTERVALO_MINUTOS", "60"))
    EXECUTAR_IMEDIATAMENTE: bool = os.getenv("BOT_EXECUTAR_AGORA", "true").lower() == "true"
    
    # ============================================
    # PERÍODO DE BUSCA
    # ============================================
    DIAS_RETROATIVOS: int = int(os.getenv("BOT_DIAS_RETROATIVOS", "30"))
    
    # ============================================
    # LOGGING (Padrões MCP)
    # ============================================
    LOG_LEVEL: str = os.getenv("BOT_LOG_LEVEL", "INFO").upper()
    LOG_FILE: Path = BOT_ROOT / "logs" / "bot.log"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
    
    # Criar diretório de logs se não existir
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # ============================================
    # RETRY E RESILIÊNCIA
    # ============================================
    MAX_RETRIES: int = int(os.getenv("BOT_MAX_RETRIES", "3"))
    RETRY_DELAY_SECONDS: int = int(os.getenv("BOT_RETRY_DELAY", "5"))
    TIMEOUT_REQUESTS: int = int(os.getenv("BOT_TIMEOUT", "60"))
    
    # ============================================
    # CERTIFICADO (Criptografia)
    # ============================================
    CERTIFICATE_ENCRYPTION_KEY: Optional[str] = os.getenv("CERTIFICATE_ENCRYPTION_KEY")
    
    # ============================================
    # VALIDAÇÃO INICIAL
    # ============================================
    @classmethod
    def validate(cls) -> bool:
        """
        Valida todas as configurações críticas.
        
        Raises:
            ValueError: Se configurações críticas estiverem faltando
        """
        cls.validate_supabase()
        return True


# Instância global
config = BotConfig()
