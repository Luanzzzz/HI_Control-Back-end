"""
Endpoints para monitorar e controlar o bot de busca automática

Seguindo padrões MCP:
- Tool Pattern: Endpoints bem definidos
- Error Handling: Robusto e informativo
- Logging: Estruturado
"""

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client
from datetime import datetime, timedelta
from typing import Dict
import logging

from app.dependencies import get_current_user, get_admin_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bot", tags=["Bot Status"])


@router.get("/status")
async def obter_status_bot(
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Retorna status geral do bot de busca automática.
    
    Verifica:
    - Última sincronização (baseada na última nota importada)
    - Quantidade de notas nas últimas 24h
    - Status do bot (ok, atrasado, nunca_executado)
    
    **Requer autenticação**
    
    Returns:
        {
            "success": true,
            "data": {
                "status": "ok" | "atrasado" | "nunca_executado",
                "ultima_sincronizacao": "2026-02-10T14:30:00Z",
                "notas_24h": 24,
                "funcionando": true
            }
        }
    """
    try:
        user_id = usuario.get("id")

        # Buscar empresas do usuario (com todos os campos para checar certificados)
        response_empresas = db.table("empresas")\
            .select("id, certificado_a1, certificado_validade")\
            .eq("usuario_id", user_id)\
            .eq("ativo", True)\
            .execute()

        empresas_data = response_empresas.data or []
        empresas_ids = [e["id"] for e in empresas_data]

        # Contagem de certificados
        agora = datetime.now()
        count_sem_cert = 0
        count_cert_expirado = 0

        for emp in empresas_data:
            cert_a1 = emp.get("certificado_a1")
            cert_val = emp.get("certificado_validade")

            if not cert_a1 and not cert_val:
                count_sem_cert += 1
                continue

            if cert_val:
                try:
                    val_dt = datetime.fromisoformat(
                        str(cert_val).replace("Z", "+00:00")
                    )
                    val_naive = val_dt.replace(tzinfo=None) if val_dt.tzinfo else val_dt
                    if val_naive < agora:
                        count_cert_expirado += 1
                except (ValueError, TypeError):
                    pass

        ultima_sincronizacao = None
        quantidade_24h = 0

        if empresas_ids:
            # 1. Buscar última nota importada (última execução do bot)
            response_ultima = db.table("notas_fiscais")\
                .select("created_at")\
                .in_("empresa_id", empresas_ids)\
                .order("created_at", desc=True)\
                .limit(1)\
                .execute()

            if response_ultima.data:
                ultima_sincronizacao = response_ultima.data[0].get("created_at")

            # 2. Contar notas nas últimas 24h
            ontem = datetime.now() - timedelta(days=1)

            response_24h = db.table("notas_fiscais")\
                .select("id", count="exact")\
                .in_("empresa_id", empresas_ids)\
                .gte("created_at", ontem.isoformat())\
                .execute()

            quantidade_24h = response_24h.count or 0
        
        # 3. Determinar status do bot
        status_bot = "ok"
        funcionando = True
        
        # Se todas as empresas estao sem certificado ou com certificado expirado
        total_empresas = len(empresas_data)
        if total_empresas > 0 and (count_sem_cert + count_cert_expirado) >= total_empresas:
            status_bot = "erro_credenciais"
            funcionando = False
        elif ultima_sincronizacao:
            # Converter para datetime
            if isinstance(ultima_sincronizacao, str):
                ultima_dt = datetime.fromisoformat(
                    ultima_sincronizacao.replace('Z', '+00:00')
                )
            else:
                ultima_dt = ultima_sincronizacao
            
            # Se não é timezone-aware, assumir UTC
            if ultima_dt.tzinfo is None:
                tz = datetime.now().astimezone().tzinfo
                ultima_dt = ultima_dt.replace(tzinfo=tz)
            
            diferenca = datetime.now(ultima_dt.tzinfo) - ultima_dt
            
            # Se não sincronizou nas últimas 2 horas, considerar problema
            if diferenca > timedelta(hours=2):
                status_bot = "atrasado"
                funcionando = False
        else:
            status_bot = "nunca_executado"
            funcionando = False
        
        return {
            "success": True,
            "data": {
                "status": status_bot,
                "ultima_sincronizacao": ultima_sincronizacao,
                "notas_24h": quantidade_24h,
                "funcionando": funcionando,
                "empresas_sem_certificado": count_sem_cert,
                "empresas_cert_expirado": count_cert_expirado
            }
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter status do bot: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter status do bot: {str(e)}"
        )


@router.get("/empresas/{empresa_id}/status")
async def obter_status_empresa(
    empresa_id: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Retorna status de sincronização de uma empresa específica.
    
    **Requer autenticação**
    
    Args:
        empresa_id: UUID da empresa
        
    Returns:
        {
            "success": true,
            "data": {
                "empresa_id": "uuid",
                "total_notas": 150,
                "ultima_nota": {
                    "created_at": "2026-02-10T14:30:00Z",
                    "tipo": "NFS-e",
                    "numero": "124"
                },
                "sincronizado": true
            }
        }
    """
    try:
        user_id = usuario.get("id")
        
        # VALIDAÇÃO DE SEGURANÇA: Verificar se empresa pertence ao usuário
        empresa_check = db.table("empresas")\
            .select("id")\
            .eq("id", empresa_id)\
            .eq("usuario_id", user_id)\
            .eq("ativo", True)\
            .maybe_single()\
            .execute()
        
        if not empresa_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada ou não pertence ao seu escritório"
            )
        
        # Buscar última nota da empresa (agora validada)
        response_ultima = db.table("notas_fiscais")\
            .select("created_at, tipo, numero")\
            .eq("empresa_id", empresa_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        
        # Contar total de notas da empresa
        response_total = db.table("notas_fiscais")\
            .select("id", count="exact")\
            .eq("empresa_id", empresa_id)\
            .execute()
        
        total_notas = response_total.count or 0
        ultima_nota = response_ultima.data[0] if response_ultima.data else None
        
        return {
            "success": True,
            "data": {
                "empresa_id": empresa_id,
                "total_notas": total_notas,
                "ultima_nota": ultima_nota,
                "sincronizado": bool(ultima_nota)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Erro ao obter status da empresa {empresa_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter status da empresa: {str(e)}"
        )


@router.post("/sincronizar-agora")
async def forcar_sincronizacao(
    usuario: dict = Depends(get_current_user)
):
    """
    Dispara sincronização manual do bot.
    
    **Nota:** O bot roda independentemente via APScheduler.
    Este endpoint apenas registra a solicitação. O bot executará
    na próxima execução agendada (normalmente dentro de 1 hora).
    
    **Requer autenticação**
    
    Returns:
        {
            "success": true,
            "message": "Sincronização será executada em breve pelo bot automático"
        }
    """
    try:
        user_id = usuario.get('id')
        logger.info(f"Usuário {user_id} solicitou sincronização manual")

        # Em produção, pode enviar sinal para bot executar imediatamente
        # Por enquanto, apenas retornar que vai executar em breve

        return {
            "success": True,
            "message": (
                "Sincronização será executada em breve pelo bot automático"
            )
        }
        
    except Exception as e:
        logger.error(f"Erro ao forçar sincronização: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao forçar sincronização: {str(e)}"
        )


@router.get("/metricas")
async def obter_metricas_bot(
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Retorna métricas detalhadas do bot filtradas por usuario.
    
    Otimizado: busca apenas campos necessarios e filtra por empresas do usuario.
    
    **Requer autenticação**
    
    Returns:
        {
            "success": true,
            "data": {
                "total_notas": 500,
                "notas_por_tipo": {"NFS-e": 350, "NF-e": 150},
                "empresas_sincronizadas": 10
            }
        }
    """
    try:
        user_id = usuario.get("id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario nao identificado"
            )

        # 1. Buscar IDs das empresas do usuario
        response_empresas = db.table("empresas")\
            .select("id")\
            .eq("usuario_id", user_id)\
            .eq("ativo", True)\
            .execute()

        empresas_ids = [e["id"] for e in (response_empresas.data or [])]

        if not empresas_ids:
            return {
                "success": True,
                "data": {
                    "total_notas": 0,
                    "notas_por_tipo": {},
                    "empresas_sincronizadas": 0
                }
            }

        # 2. Total de notas (count apenas, sem buscar registros)
        response_total = db.table("notas_fiscais")\
            .select("id", count="exact")\
            .in_("empresa_id", empresas_ids)\
            .execute()

        total_notas = response_total.count or 0

        # 3. Notas por tipo - buscar apenas campo 'tipo' (leve)
        response_tipos = db.table("notas_fiscais")\
            .select("tipo")\
            .in_("empresa_id", empresas_ids)\
            .execute()

        tipos_count: Dict[str, int] = {}
        for nota in response_tipos.data or []:
            tipo = nota.get("tipo", "Desconhecido")
            tipos_count[tipo] = tipos_count.get(tipo, 0) + 1

        # 4. Empresas sincronizadas - buscar apenas empresa_id distinto
        response_empresas_sync = db.table("notas_fiscais")\
            .select("empresa_id")\
            .in_("empresa_id", empresas_ids)\
            .execute()

        empresas_com_notas = set(
            n.get("empresa_id")
            for n in (response_empresas_sync.data or [])
            if n.get("empresa_id")
        )

        return {
            "success": True,
            "data": {
                "total_notas": total_notas,
                "notas_por_tipo": tipos_count,
                "empresas_sincronizadas": len(empresas_com_notas)
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter métricas do bot: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter métricas: {str(e)}"
        )
