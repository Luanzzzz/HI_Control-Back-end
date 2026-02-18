"""
Rate Limiter dinamico por plano de usuario.

O contador persistente de consultas do buscador foi removido.
Mantemos fallback sem estado para evitar dependencia em tabelas excluidas.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict
from fastapi import HTTPException, status

from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)


RATE_LIMITS: Dict[str, int] = {
    "free": 10,
    "basico": 20,
    "premium": 50,
    "enterprise": 1000,
}

DEFAULT_LIMIT = 10


class RateLimiter:
    def __init__(self):
        self.db = supabase_admin
        self.window_hours = 1

    async def get_user_limit(self, user_id: str) -> int:
        try:
            response = (
                self.db.table("assinaturas")
                .select("planos(nome)")
                .eq("usuario_id", user_id)
                .eq("status", "ativa")
                .execute()
            )
            if response.data and len(response.data) > 0:
                plano_nome = response.data[0].get("planos", {}).get("nome", "free")
                return RATE_LIMITS.get(plano_nome.lower(), DEFAULT_LIMIT)
            return DEFAULT_LIMIT
        except Exception as e:
            logger.warning(f"Erro ao buscar plano do usuario: {e}")
            return DEFAULT_LIMIT

    async def get_current_count(self, user_id: str, empresa_id: str) -> int:
        return 0

    async def check_rate_limit(self, user_id: str, empresa_id: str) -> Dict[str, any]:
        limit = await self.get_user_limit(user_id)
        current = await self.get_current_count(user_id, empresa_id)
        remaining = max(0, limit - current)

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
                    "retry_after_seconds": int((reset_at - now).total_seconds()),
                },
                headers={
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": reset_at.isoformat(),
                    "Retry-After": str(int((reset_at - now).total_seconds())),
                },
            )

        return {
            "allowed": True,
            "limit": limit,
            "current": current,
            "remaining": remaining,
            "reset_at": reset_at.isoformat(),
        }

    async def get_rate_limit_headers(self, user_id: str, empresa_id: str) -> Dict[str, str]:
        try:
            limit = await self.get_user_limit(user_id)
            current = await self.get_current_count(user_id, empresa_id)
            remaining = max(0, limit - current)

            now = datetime.now()
            reset_at = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

            return {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": reset_at.isoformat(),
            }
        except Exception:
            return {}


rate_limiter = RateLimiter()
