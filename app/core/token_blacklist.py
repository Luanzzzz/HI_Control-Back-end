"""
Gerenciador de blacklist de tokens JWT com TTL automático.
Implementação thread-safe em memória para logout e revogação de tokens.
"""
import time
from threading import Lock
import logging

logger = logging.getLogger(__name__)


class TokenBlacklist:
    """
    Blacklist de tokens JWT com limpeza automática de tokens expirados.
    Usa jti (JWT ID) para identificar tokens individualmente.
    """
    def __init__(self):
        self._blacklist: dict[str, float] = {}  # jti -> expiry_timestamp
        self._lock = Lock()

    def add(self, jti: str, expires_at: float) -> None:
        """
        Adiciona um token à blacklist.

        Args:
            jti: JWT ID (campo jti do token)
            expires_at: Timestamp de expiração do token (campo exp do token)
        """
        with self._lock:
            self._blacklist[jti] = expires_at
            self._cleanup()
            logger.info(f"[BLACKLIST] Token {jti[:8]}... adicionado à blacklist")

    def is_blacklisted(self, jti: str) -> bool:
        """
        Verifica se um token está na blacklist.

        Args:
            jti: JWT ID (campo jti do token)

        Returns:
            True se token está na blacklist, False caso contrário
        """
        with self._lock:
            return jti in self._blacklist

    def _cleanup(self) -> None:
        """
        Remove tokens expirados da blacklist (sincronizado automaticamente).
        Chamado a cada adição de token.
        """
        now = time.time()
        expired = [k for k, v in self._blacklist.items() if v < now]
        for k in expired:
            del self._blacklist[k]

        if expired:
            logger.debug(f"[BLACKLIST] Limpeza: {len(expired)} tokens expirados removidos")


# Instância global thread-safe
token_blacklist = TokenBlacklist()
