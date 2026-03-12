"""
Proteção contra emissão acidental de documentos fiscais em produção.

Objetivo: Impedir que testes automatizados, CI/CD ou chamadas inadvertidas
emitam notas fiscais válidas na Receita Federal, o que geraria problemas
fiscais para o cliente e necessidade de cancelamento formal.

Autor: Claude Sonnet 4.5
Data: 2026-03-12
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class EmissionBlockedError(RuntimeError):
    """
    Erro levantado quando emissão em produção é bloqueada por configuração de segurança.
    """
    pass


def verificar_permissao_emissao(
    empresa_id: str,
    tipo_documento: str = "NFe",
    raise_on_block: bool = True
) -> bool:
    """
    Verifica se a emissão de documento fiscal em produção é permitida.

    Esta função implementa múltiplas camadas de proteção contra emissão acidental:
    1. Ambiente de testes NUNCA pode emitir em produção
    2. Produção requer flag explícita ALLOW_PRODUCTION_EMISSION=true
    3. Homologação sempre permitida (sem riscos)

    Args:
        empresa_id: UUID da empresa emitente (para auditoria)
        tipo_documento: Tipo do documento fiscal (NFe, NFSe, NFCe, CTe)
        raise_on_block: Se True, levanta exceção; se False, retorna boolean

    Returns:
        True se emissão permitida, False se bloqueada (apenas se raise_on_block=False)

    Raises:
        EmissionBlockedError: Se emissão bloqueada e raise_on_block=True

    Example:
        >>> # No início do método de autorização/emissão:
        >>> verificar_permissao_emissao(empresa_id="uuid-123", tipo_documento="NFe")
        >>> # Prossegue apenas se permitido
    """
    from app.core.config import settings

    sefaz_ambiente = settings.SEFAZ_AMBIENTE
    allow_production = settings.ALLOW_PRODUCTION_EMISSION
    environment = settings.ENVIRONMENT

    # =========================================================================
    # CASO 1: Homologação sempre permitida (sem riscos)
    # =========================================================================
    if sefaz_ambiente != "producao":
        logger.debug(
            f"✅ Emissão {tipo_documento} permitida - Ambiente: {sefaz_ambiente} (homologação)"
        )
        return True

    # =========================================================================
    # CASO 2: Ambiente de testes NUNCA pode emitir em produção
    # =========================================================================
    if environment == "test":
        erro_msg = (
            "\n\n" + "=" * 80 + "\n"
            "🔴 EMISSÃO BLOQUEADA - PROTEÇÃO DE SEGURANÇA\n"
            "=" * 80 + "\n\n"
            f"Tentativa de emitir {tipo_documento} em PRODUÇÃO durante execução de TESTES.\n\n"
            "MOTIVO DO BLOQUEIO:\n"
            "  - SEFAZ_AMBIENTE = producao\n"
            "  - ENVIRONMENT = test\n\n"
            "AÇÃO CORRETIVA:\n"
            "  1. Configure SEFAZ_AMBIENTE=homologacao para testes\n"
            "  2. OU use mocks do SEFAZ em testes automatizados\n"
            "  3. NUNCA execute testes com SEFAZ_AMBIENTE=producao\n\n"
            f"Empresa: {empresa_id}\n"
            f"Documento: {tipo_documento}\n"
            "=" * 80 + "\n\n"
        )

        logger.error(erro_msg)

        if raise_on_block:
            raise EmissionBlockedError(erro_msg)
        return False

    # =========================================================================
    # CASO 3: Produção requer flag explícita
    # =========================================================================
    if not allow_production:
        erro_msg = (
            "\n\n" + "=" * 80 + "\n"
            "🔴 EMISSÃO BLOQUEADA - PROTEÇÃO DE SEGURANÇA\n"
            "=" * 80 + "\n\n"
            f"Tentativa de emitir {tipo_documento} em PRODUÇÃO sem autorização explícita.\n\n"
            "MOTIVO DO BLOQUEIO:\n"
            "  - SEFAZ_AMBIENTE = producao\n"
            "  - ALLOW_PRODUCTION_EMISSION = false\n\n"
            "AÇÃO CORRETIVA:\n"
            "  Para habilitar emissão em produção:\n"
            "  1. Configure ALLOW_PRODUCTION_EMISSION=true no .env ou secrets\n"
            "  2. Verifique que ENVIRONMENT=production\n"
            "  3. Confirme que certificado A1 é de PRODUÇÃO (não homologação)\n\n"
            "IMPORTANTE:\n"
            "  Esta proteção existe para evitar emissão acidental em produção\n"
            "  durante testes, CI/CD ou desenvolvimento.\n\n"
            f"Empresa: {empresa_id}\n"
            f"Documento: {tipo_documento}\n"
            "=" * 80 + "\n\n"
        )

        logger.error(erro_msg)

        if raise_on_block:
            raise EmissionBlockedError(erro_msg)
        return False

    # =========================================================================
    # CASO 4: Produção autorizada — LOG DE AUDITORIA
    # =========================================================================
    logger.warning(
        "🟡 EMISSÃO EM PRODUÇÃO AUTORIZADA - "
        f"Empresa: {empresa_id} | "
        f"Documento: {tipo_documento} | "
        f"Ambiente: {sefaz_ambiente} | "
        f"ALLOW_PRODUCTION_EMISSION: {allow_production}"
    )

    # Auditoria adicional: registrar em tabela de auditoria (se disponível)
    try:
        _registrar_auditoria_emissao_producao(empresa_id, tipo_documento)
    except Exception as e:
        logger.warning(f"Falha ao registrar auditoria de emissão: {e}")

    return True


def _registrar_auditoria_emissao_producao(
    empresa_id: str,
    tipo_documento: str
) -> None:
    """
    Registra em tabela de auditoria que houve emissão em produção.

    IMPORTANTE: Falha silenciosa — não bloqueia emissão se auditoria falhar.
    """
    try:
        from datetime import datetime
        from app.db.supabase_client import supabase_admin

        auditoria_data = {
            "empresa_id": empresa_id,
            "tipo_documento": tipo_documento,
            "ambiente": "producao",
            "timestamp": datetime.now().isoformat(),
            "action": "emission_production_allowed",
            "user_id": None,  # Será preenchido pelo endpoint se disponível
        }

        # Tentar inserir na tabela de auditoria (se existir)
        supabase_admin.table("audit_log").insert(auditoria_data).execute()

        logger.info(f"✅ Auditoria de emissão registrada: {empresa_id} - {tipo_documento}")

    except Exception as e:
        # Não bloquear emissão se auditoria falhar
        logger.debug(f"Auditoria de emissão não registrada: {e}")


# ============================================
# HELPERS PARA VALIDAÇÃO EM TESTES
# ============================================

def ambiente_e_homologacao() -> bool:
    """
    Verifica se ambiente SEFAZ é homologação.

    Returns:
        True se homologação, False se produção

    Example:
        >>> if not ambiente_e_homologacao():
        ...     pytest.skip("Teste apenas em homologação")
    """
    from app.core.config import settings
    return settings.SEFAZ_AMBIENTE != "producao"


def forcar_ambiente_homologacao() -> None:
    """
    Força ambiente SEFAZ para homologação (útil em setup de testes).

    ATENÇÃO: Apenas usar em fixtures de teste, nunca em produção.
    """
    os.environ["SEFAZ_AMBIENTE"] = "homologacao"
    logger.info("🧪 Ambiente SEFAZ forçado para HOMOLOGAÇÃO (testes)")


def resetar_cache_settings() -> None:
    """
    Limpa cache de settings para recarregar variáveis de ambiente.

    Útil em testes que modificam variáveis de ambiente.
    """
    from app.core.config import get_settings
    get_settings.cache_clear()
    logger.debug("Settings cache limpo")
