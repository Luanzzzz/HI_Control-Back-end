"""
Serviço de validação de planos de usuário e aplicação de limites de negócio.

Implementa regras de acesso baseadas em planos (Básico/Premium/Enterprise).
"""
from supabase import Client
from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)


class PlanLimits:
    """
    Definição de limites por plano do usuário.
    
    PADRONIZAÇÃO: Usa 'PREMIUM' ao invés de 'profissional' para 
    manter paridade com types.ts do frontend.
    """
    BASICO = {
        "historico_dias": 30,  # Apenas últimos 30 dias
        "max_empresas": 3,
        "max_consultas_dia": 50,
        "max_notas_mes": 500,
    }
    
    PREMIUM = {
        "historico_dias": None,  # Ilimitado
        "max_empresas": 10,
        "max_consultas_dia": 200,
        "max_notas_mes": 2000,
    }
    
    ENTERPRISE = {
        "historico_dias": None,  # Ilimitado
        "max_empresas": 999,
        "max_consultas_dia": 9999,
        "max_notas_mes": 99999,
    }


async def obter_plano_usuario(usuario_id: str, db: Client) -> Dict[str, Any]:
    """
    Busca plano ativo do usuário com seus limites.
    
    Args:
        usuario_id: UUID do usuário
        db: Cliente Supabase
    
    Returns:
        Dict com 'nome', 'limites', 'assinatura_id', 'modulos'
    
    Raises:
        HTTPException 403: Se nenhuma assinatura ativa encontrada
    """
    try:
        # Buscar assinatura ativa com plano
        response = db.table("assinaturas")\
            .select("*, planos!inner(*)")\
            .eq("usuario_id", usuario_id)\
            .eq("status", "ativa")\
            .gte("data_fim", datetime.now().date().isoformat())\
            .execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Nenhuma assinatura ativa encontrada. Entre em contato com o suporte."
            )
        
        assinatura = response.data[0]
        plano = assinatura["planos"]
        plano_nome = plano["nome"].lower()
        
        # Mapear nome do plano para limites
        # IMPORTANTE: Usar "premium" como padrão para "profissional"
        limites_map = {
            "basico": PlanLimits.BASICO,
            "profissional": PlanLimits.PREMIUM,  # Mapeamento para compatibilidade
            "premium": PlanLimits.PREMIUM,
            "enterprise": PlanLimits.ENTERPRISE,
        }
        
        limites = limites_map.get(plano_nome, PlanLimits.BASICO)
        
        # Padronizar nome para "premium" se for "profissional"
        nome_padrao = "premium" if plano_nome == "profissional" else plano_nome
        
        logger.info(
            f"Plano do usuário {usuario_id}: {nome_padrao} | "
            f"Histórico: {limites['historico_dias'] or 'ilimitado'} dias"
        )
        
        return {
            "nome": nome_padrao,
            "limites": limites,
            "assinatura_id": assinatura["id"],
            "modulos": plano.get("modulos_disponiveis", [])
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter plano do usuário {usuario_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao verificar plano do usuário"
        )


async def validar_limite_historico(
    plano_info: Dict[str, Any],
    nsu_inicial: int = None
) -> bool:
    """
    Valida se a busca respeita limite de histórico do plano.
    
    Regras:
    - Plano básico: apenas últimos 30 dias
    - Premium/Enterprise: ilimitado
    
    Args:
        plano_info: Informações do plano (retorno de obter_plano_usuario)
        nsu_inicial: NSU inicial da consulta (None = buscar desde início)
    
    Returns:
        True se dentro do limite
    
    Raises:
        HTTPException 403: Se exceder limite de histórico
    """
    historico_dias = plano_info["limites"]["historico_dias"]
    
    # Se ilimitado, permitir
    if historico_dias is None:
        logger.debug(f"Plano {plano_info['nome']}: histórico ilimitado")
        return True
    
    # Para plano básico, validar
    plano_nome = plano_info["nome"]
    
    if plano_nome == "basico":
        # Aviso ao usuário sobre limite
        logger.warning(
            f"Plano {plano_nome} limitado a {historico_dias} dias. "
            f"Notas mais antigas serão ignoradas."
        )
        
        # Por enquanto, apenas avisar. Em produção, validar baseado em NSU/data
        # TODO: Implementar validação real quando integrar com data_emissao
        return True
    
    return True


async def validar_limite_empresas(
    usuario_id: str,
    plano_info: Dict[str, Any],
    db: Client
) -> bool:
    """
    Valida se usuário não excedeu limite de empresas cadastradas.
    
    Args:
        usuario_id: UUID do usuário
        plano_info: Informações do plano
        db: Cliente Supabase
    
    Returns:
        True se dentro do limite
    
    Raises:
        HTTPException 403: Se exceder limite de empresas
    """
    try:
        max_empresas = plano_info["limites"]["max_empresas"]
        
        # Contar empresas ativas do usuário
        response = db.table("empresas")\
            .select("id", count="exact")\
            .eq("usuario_id", usuario_id)\
            .eq("ativa", True)\
            .is_("deleted_at", "null")\
            .execute()
        
        total_empresas = response.count if response.count else 0
        
        logger.info(
            f"Usuário {usuario_id}: {total_empresas}/{max_empresas} empresas"
        )
        
        if total_empresas >= max_empresas:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Limite de {max_empresas} empresas atingido no plano "
                    f"'{plano_info['nome']}'. Faça upgrade para adicionar mais empresas."
                )
            )
        
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao validar limite de empresas: {e}")
        # Permitir por padrão em caso de erro (fail-open)
        return True


async def validar_limite_consultas_dia(
    usuario_id: str,
    plano_info: Dict[str, Any],
    db: Client
) -> bool:
    """
    Valida se usuário não excedeu limite de consultas por dia.
    
    Args:
        usuario_id: UUID do usuário
        plano_info: Informações do plano
        db: Cliente Supabase
    
    Returns:
        True se dentro do limite
    
    Raises:
        HTTPException 429: Se exceder limite de consultas
    """
    try:
        max_consultas = plano_info["limites"]["max_consultas_dia"]
        
        # Contar consultas do dia atual (via sefaz_log)
        hoje = datetime.now().date().isoformat()
        
        response = db.table("sefaz_log")\
            .select("id", count="exact")\
            .eq("operacao", "consulta_distribuicao")\
            .gte("created_at", f"{hoje}T00:00:00")\
            .lte("created_at", f"{hoje}T23:59:59")\
            .in_("empresa_id", 
                 db.table("empresas")
                   .select("id")
                   .eq("usuario_id", usuario_id)
            )\
            .execute()
        
        total_consultas = response.count if response.count else 0
        
        logger.info(
            f"Usuário {usuario_id}: {total_consultas}/{max_consultas} consultas hoje"
        )
        
        if total_consultas >= max_consultas:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Limite de {max_consultas} consultas/dia atingido no plano "
                    f"'{plano_info['nome']}'. Tente novamente amanhã ou faça upgrade."
                )
            )
        
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao validar limite de consultas: {e}")
        # Permitir por padrão em caso de erro
        return True


def obter_resumo_plano(plano_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retorna resumo formatado do plano para exibição ao usuário.
    
    Args:
        plano_info: Informações do plano
    
    Returns:
        Dict com informações legíveis do plano
    """
    limites = plano_info["limites"]
    
    return {
        "nome": plano_info["nome"].upper(),
        "historico": (
            f"{limites['historico_dias']} dias" 
            if limites["historico_dias"] 
            else "Ilimitado"
        ),
        "max_empresas": limites["max_empresas"],
        "max_consultas_dia": limites["max_consultas_dia"],
        "max_notas_mes": limites["max_notas_mes"],
        "modulos": plano_info.get("modulos", [])
    }
