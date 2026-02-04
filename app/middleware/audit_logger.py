"""
Audit Logger para registro de operações sensíveis.

Registra consultas SEFAZ, acesso a certificados, e operações críticas.
Conformidade LGPD: dados retidos por 90 dias.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from app.db.supabase_client import supabase_admin

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Tipos de ações auditáveis."""
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
    """
    Logger de auditoria para operações sensíveis.
    
    Registra no Supabase para persistência e conformidade.
    """
    
    def __init__(self):
        self.db = supabase_admin
        self.enabled = True
    
    async def log(
        self,
        action: AuditAction,
        user_id: str,
        empresa_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """
        Registra uma ação no log de auditoria.
        
        Args:
            action: Tipo da ação (AuditAction)
            user_id: ID do usuário que executou
            empresa_id: ID da empresa relacionada (opcional)
            details: Detalhes adicionais em JSON
            ip_address: IP do cliente
            success: Se a operação foi bem-sucedida
            error_message: Mensagem de erro se falhou
        """
        if not self.enabled:
            return
        
        try:
            # Log local para debug
            log_msg = (
                f"[AUDIT] {action.value} | "
                f"user={user_id} | "
                f"empresa={empresa_id or 'N/A'} | "
                f"success={success}"
            )
            
            if error_message:
                log_msg += f" | error={error_message}"
            
            if success:
                logger.info(log_msg)
            else:
                logger.warning(log_msg)
            
            # Registrar no banco (tabela historico_consultas para SEFAZ)
            # Para outras ações, registrar em tabela dedicada se necessário
            if action in [AuditAction.SEFAZ_CONSULTA, AuditAction.SEFAZ_ERRO]:
                # Já registrado pelo endpoint
                pass
            elif action == AuditAction.CERTIFICADO_FALLBACK:
                # Registrar uso de fallback
                if empresa_id and details:
                    self.db.table("historico_consultas").insert({
                        "empresa_id": empresa_id,
                        "contador_id": user_id,
                        "filtros": {"_audit": "certificado_fallback"},
                        "quantidade_notas": 0,
                        "fonte": "cache",
                        "tempo_resposta_ms": 0,
                        "sucesso": success,
                        "erro_mensagem": error_message,
                        "certificado_tipo": "contador_fallback"
                    }).execute()
            
        except Exception as e:
            # Nunca falhar por causa de audit logging
            logger.error(f"Erro no audit log: {e}")
    
    async def log_sefaz_consulta(
        self,
        user_id: str,
        empresa_id: str,
        cnpj: str,
        notas_encontradas: int,
        fonte: str,
        tempo_ms: int,
        certificado_tipo: str = "empresa"
    ):
        """Helper específico para consultas SEFAZ."""
        await self.log(
            action=AuditAction.SEFAZ_CONSULTA,
            user_id=user_id,
            empresa_id=empresa_id,
            details={
                "cnpj": cnpj,
                "notas_encontradas": notas_encontradas,
                "fonte": fonte,
                "tempo_ms": tempo_ms,
                "certificado_tipo": certificado_tipo
            },
            success=True
        )
    
    async def log_certificado_usado(
        self,
        user_id: str,
        empresa_id: str,
        tipo: str,  # "empresa" ou "contador_fallback"
        warning: Optional[str] = None
    ):
        """Helper para registrar qual certificado foi usado."""
        action = (
            AuditAction.CERTIFICADO_FALLBACK 
            if tipo == "contador_fallback" 
            else AuditAction.CERTIFICADO_ACESSO
        )
        
        await self.log(
            action=action,
            user_id=user_id,
            empresa_id=empresa_id,
            details={
                "tipo": tipo,
                "warning": warning
            },
            success=True
        )
    
    async def log_erro_sefaz(
        self,
        user_id: str,
        empresa_id: str,
        codigo: str,
        mensagem: str
    ):
        """Helper para erros de comunicação com SEFAZ."""
        await self.log(
            action=AuditAction.SEFAZ_ERRO,
            user_id=user_id,
            empresa_id=empresa_id,
            details={
                "codigo": codigo,
                "mensagem": mensagem
            },
            success=False,
            error_message=mensagem
        )


# Instância singleton
audit_logger = AuditLogger()
