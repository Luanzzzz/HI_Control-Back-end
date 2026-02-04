"""
Rate Limiter dinâmico por plano de usuário.

Implementa limitação de consultas SEFAZ baseado no plano contratado.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict
from fastapi import HTTPException, Request, status

from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)


# Limites por plano (consultas/hora)
RATE_LIMITS: Dict[str, int] = {
    "free": 10,
    "basico": 20,
    "premium": 50,
    "enterprise": 1000  # Praticamente ilimitado
}

# Default para planos desconhecidos
DEFAULT_LIMIT = 10


class RateLimiter:
    """
    Rate limiter dinâmico baseado no plano do usuário.
    
    Armazena contagens no Supabase para persistência.
    """
    
    def __init__(self):
        self.db = supabase_admin
        self.window_hours = 1  # Janela de 1 hora
    
    def _get_cache_key(self, user_id: str, empresa_id: str) -> str:
        """Gera chave para controle de rate limit."""
        hora_atual = datetime.now().strftime("%Y-%m-%d-%H")
        return f"rate:{user_id}:{empresa_id}:{hora_atual}"
    
    async def get_user_limit(self, user_id: str) -> int:
        """
        Retorna limite de consultas por hora baseado no plano.
        """
        try:
            # Buscar plano do usuário via assinatura ativa
            response = self.db.table("assinaturas")\
                .select("planos(nome)")\
                .eq("usuario_id", user_id)\
                .eq("status", "ativa")\
                .execute()
            
            if response.data and len(response.data) > 0:
                plano_nome = response.data[0].get("planos", {}).get("nome", "free")
                return RATE_LIMITS.get(plano_nome.lower(), DEFAULT_LIMIT)
            
            return DEFAULT_LIMIT
            
        except Exception as e:
            logger.warning(f"Erro ao buscar plano do usuário: {e}")
            return DEFAULT_LIMIT
    
    async def get_current_count(
        self, 
        user_id: str, 
        empresa_id: str
    ) -> int:
        """
        Retorna contagem atual de consultas na janela.
        """
        try:
            # Buscar consultas na última hora
            uma_hora_atras = (datetime.now() - timedelta(hours=1)).isoformat()
            
            response = self.db.table("historico_consultas")\
                .select("id", count="exact")\
                .eq("contador_id", user_id)\
                .eq("empresa_id", empresa_id)\
                .eq("fonte", "sefaz")\
                .gte("created_at", uma_hora_atras)\
                .execute()
            
            return response.count if response.count else 0
            
        except Exception as e:
            logger.warning(f"Erro ao contar requisições: {e}")
            return 0
    
    async def check_rate_limit(
        self,
        user_id: str,
        empresa_id: str
    ) -> Dict[str, any]:
        """
        Verifica se usuário pode fazer mais consultas.
        
        Returns:
            Dict com allowed (bool), remaining (int), reset_at (str)
        
        Raises:
            HTTPException 429 se limite excedido
        """
        limit = await self.get_user_limit(user_id)
        current = await self.get_current_count(user_id, empresa_id)
        remaining = max(0, limit - current)
        
        # Calcular próximo reset (início da próxima hora)
        now = datetime.now()
        reset_at = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        
        if current >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "error": "rate_limit_exceeded",
                    "mensagem": f"Limite de {limit} consultas/hora excedido para esta empresa",
                    "limit": limit,
                    "current": current,
                    "reset_at": reset_at.isoformat(),
                    "retry_after_seconds": int((reset_at - now).total_seconds())
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": reset_at.isoformat(),
                    "Retry-After": str(int((reset_at - now).total_seconds()))
                }
            )
        
        return {
            "allowed": True,
            "limit": limit,
            "current": current,
            "remaining": remaining,
            "reset_at": reset_at.isoformat()
        }
    
    async def get_rate_limit_headers(
        self,
        user_id: str,
        empresa_id: str
    ) -> Dict[str, str]:
        """
        Retorna headers de rate limit para incluir na resposta.
        """
        try:
            limit = await self.get_user_limit(user_id)
            current = await self.get_current_count(user_id, empresa_id)
            remaining = max(0, limit - current)
            
            now = datetime.now()
            reset_at = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            
            return {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": reset_at.isoformat()
            }
        except:
            return {}


# Instância singleton
rate_limiter = RateLimiter()
