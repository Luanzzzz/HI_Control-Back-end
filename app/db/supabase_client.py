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

# Factory functions com lazy initialization
def get_supabase_client() -> Client:
    """
    Obtém cliente Supabase para operações com RLS.
    Lança RuntimeError se a inicialização falhar.
    """
    try:
        return SupabaseManager.get_client()
    except Exception as e:
        raise RuntimeError(f"Supabase client não inicializado: {e}") from e

def get_supabase_admin() -> Client:
    """
    Obtém cliente Supabase Admin para operações que ignoram RLS.
    Lança RuntimeError se a inicialização falhar.

    ⚠️ ATENÇÃO: Usar apenas em operações backend que requerem bypass de RLS.
    """
    try:
        return SupabaseManager.get_admin()
    except Exception as e:
        raise RuntimeError(f"Supabase admin client não inicializado: {e}") from e

@lru_cache()
def get_supabase_admin_client() -> Client:
    """
    Cria e retorna cliente Supabase com privilégios administrativos (cached).
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
        raise RuntimeError(f"Supabase admin client não inicializado: {e}") from e


# Variáveis globais para compatibilidade com imports diretos
# Inicializadas via lazy evaluation na primeira vez que forem acessadas
# Nota: Imports diretos como `from app.db.supabase_client import supabase_client`
# devem ser evitados. Prefira usar as dependências FastAPI com Depends().
_supabase_client_cache: Client | None = None
_supabase_admin_cache: Client | None = None

def _get_cached_client() -> Client:
    global _supabase_client_cache
    if _supabase_client_cache is None:
        _supabase_client_cache = get_supabase_client()
    return _supabase_client_cache

def _get_cached_admin() -> Client:
    global _supabase_admin_cache
    if _supabase_admin_cache is None:
        _supabase_admin_cache = get_supabase_admin()
    return _supabase_admin_cache

# Propriedades para acesso estilo atributo global
class _ClientProxy:
    def __getattr__(self, name: str):
        return getattr(_get_cached_client(), name)

class _AdminProxy:
    def __getattr__(self, name: str):
        return getattr(_get_cached_admin(), name)

supabase_client = _ClientProxy()
supabase_admin = _AdminProxy()
