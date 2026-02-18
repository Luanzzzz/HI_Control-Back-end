"""
Audit Logger para registro de operacoes sensiveis.

Persistencia em historico do buscador foi removida.
Mantemos logging aplicacional sem dependencia de tabelas excluidas.
"""
import logging
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    SEFAZ_CONSULTA = "sefaz_consulta"
    SEFAZ_ERRO = "sefaz_erro"
    CERTIFICADO_ACESSO = "certificado_acesso"
    CERTIFICADO_UPLOAD = "certificado_upload"
    CERTIFICADO_FALLBACK = "certificado_fallback"
    LOGIN = "login"
    LOGOUT = "logout"
    EMPRESA_CRIADA = "empresa_criada"
    EMPRESA_DELETADA = "empresa_deletada"


class AuditLogger:
    def __init__(self):
        self.enabled = True

    async def log(
        self,
        action: AuditAction,
        user_id: str,
        empresa_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ):
        if not self.enabled:
            return

        log_msg = (
            f"[AUDIT] {action.value} | "
            f"user={user_id} | "
            f"empresa={empresa_id or 'N/A'} | "
            f"success={success}"
        )

        if error_message:
            log_msg += f" | error={error_message}"
        if details:
            log_msg += f" | details={details}"
        if ip_address:
            log_msg += f" | ip={ip_address}"

        if success:
            logger.info(log_msg)
        else:
            logger.warning(log_msg)

    async def log_sefaz_consulta(
        self,
        user_id: str,
        empresa_id: str,
        cnpj: str,
        notas_encontradas: int,
        fonte: str,
        tempo_ms: int,
        certificado_tipo: str = "empresa",
    ):
        await self.log(
            action=AuditAction.SEFAZ_CONSULTA,
            user_id=user_id,
            empresa_id=empresa_id,
            details={
                "cnpj": cnpj,
                "notas_encontradas": notas_encontradas,
                "fonte": fonte,
                "tempo_ms": tempo_ms,
                "certificado_tipo": certificado_tipo,
            },
            success=True,
        )

    async def log_certificado_usado(
        self,
        user_id: str,
        empresa_id: str,
        tipo: str,
        warning: Optional[str] = None,
    ):
        action = (
            AuditAction.CERTIFICADO_FALLBACK
            if tipo == "contador_fallback"
            else AuditAction.CERTIFICADO_ACESSO
        )
        await self.log(
            action=action,
            user_id=user_id,
            empresa_id=empresa_id,
            details={"tipo": tipo, "warning": warning},
            success=True,
        )

    async def log_erro_sefaz(
        self,
        user_id: str,
        empresa_id: str,
        codigo: str,
        mensagem: str,
    ):
        await self.log(
            action=AuditAction.SEFAZ_ERRO,
            user_id=user_id,
            empresa_id=empresa_id,
            details={"codigo": codigo, "mensagem": mensagem},
            success=False,
            error_message=mensagem,
        )


audit_logger = AuditLogger()
