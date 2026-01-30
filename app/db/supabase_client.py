from supabase import create_client, Client
from app.core.config import settings
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)

class SupabaseManager:
    _client: Client | None = None
    _admin: Client | None = None

    @classmethod
    def get_client(cls) -> Client:
        if cls._client is None:
            try:
                cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            except Exception as e:
                logger.error(f"FATAL: Falha ao inicializar Supabase Client: {e}")
                # Não relançar erro aqui para não crashar o app inteiro, mas vai falhar nas rotas
                raise e
        return cls._client

    @classmethod
    def get_admin(cls) -> Client:
        if cls._admin is None:
            try:
                cls._admin = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
            except Exception as e:
                logger.error(f"FATAL: Falha ao inicializar Supabase Admin: {e}")
                raise e
        return cls._admin

# Proxies seguros para manter compatibilidade, mas ideais seriam calls de função
# ATENÇÃO: Acessar estas variáveis diretamente ainda pode causar crash na primeira vez se não for tratado.
# Melhor usar get_client() nas dependências.

# Inicialização LAZY segura
def get_supabase_client() -> Client:
    return SupabaseManager.get_client()

def get_supabase_admin() -> Client:
    return SupabaseManager.get_admin()

# Varáveis legadas para compatibilidade (mantidas, mas inicializadas sob demanda seria melhor)
# Por ora, vamos instanciar aqui, mas envolver em try/except global para não matar o app
try:
    supabase_client = SupabaseManager.get_client()
    supabase_admin = SupabaseManager.get_admin()
except Exception as e:
    logger.critical(f"CRASH EVITADO: Supabase não inicializou: {e}")
    supabase_client = None
    supabase_admin = None

@lru_cache()
def get_supabase_admin_client() -> Client:
    """
    Cria e retorna cliente Supabase com privilégios administrativos.
    Utiliza a service role key para operações que ignoram RLS.

    ⚠️ ATENÇÃO: Usar apenas em operações backend que requerem bypass de RLS.
    """
    try:
        supabase: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY
        )
        logger.info("Cliente Supabase Admin inicializado com sucesso")
        return supabase
    except Exception as e:
        logger.error(f"Erro ao inicializar Supabase Admin: {e}")
        raise


# Instâncias globais (serão usadas como dependências FastAPI)
supabase_client = get_supabase_client()
supabase_admin = get_supabase_admin_client()
