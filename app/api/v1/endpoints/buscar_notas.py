"""
Endpoint REST para busca de notas fiscais distribuídas (DistribuicaoDFe).

Permite consultar NFes pelo CNPJ sem necessidade de certificado digital.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from supabase import Client
from typing import Optional
import logging

from app.models.nfe_busca import (
    ConsultaDistribuicaoRequest,
    DistribuicaoResponseModel,
    NFeBuscadaMetadata,
)
from app.services.sefaz_service import sefaz_service, SefazException
from app.dependencies import get_current_user, get_admin_db, verificar_acesso_modulo
from app.services.plan_validation import (
    obter_plano_usuario,
    validar_limite_historico,
    validar_limite_consultas_dia,
    obter_resumo_plano
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfe", tags=["NFe - Busca"])


# ============================================
# ENDPOINT PRINCIPAL
# ============================================

@router.post(
    "/buscar",
    response_model=dict,
    summary="Buscar notas fiscais distribuídas",
    description="""
    Consulta NFes distribuídas pela SEFAZ para um CNPJ específico.
    
    **Não requer certificado digital** - Consulta pública via DistribuicaoDFe.
    
    **Limites por plano:**
    - Básico: Últimos 30 dias, máx 3 empresas
    - Premium: Ilimitado, máx 10 empresas
    - Enterprise: Ilimitado, máx 999 empresas
    
    **Retorna:**
    - Lista de notas encontradas com metadados
    - NSU para continuação de consultas
    - Total de notas
    """,
)
async def buscar_notas_fiscais(
    request: ConsultaDistribuicaoRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Busca NFes distribuídas pela SEFAZ para um CNPJ.
    
    Args:
        request: Dados da consulta (CNPJ, NSU inicial, etc)
        current_user: Usuário autenticado
        db: Cliente Supabase admin
    
    Returns:
        Dict com lista de notas, NSU e estatísticas
    
    Raises:
        HTTPException: Em caso de erro na consulta
    """
    try:
        logger.info(
            f"[BUSCA NFe] Usuário: {current_user.get('email')} | CNPJ: {request.cnpj}"
        )
        
        # 1. Verificar acesso ao módulo
        await verificar_acesso_modulo("buscador_notas", current_user, db)
        
        # 2. Obter plano do usuário
        plano_info = await obter_plano_usuario(current_user["id"], db)
        
        logger.info(
            f"[PLANO] {plano_info['nome'].upper()} | "
            f"Histórico: {plano_info['limites']['historico_dias'] or 'ilimitado'} dias"
        )
        
        # 3. Validar limites do plano
        await validar_limite_historico(plano_info, request.nsu_inicial)
        await validar_limite_consultas_dia(current_user["id"], plano_info, db)
        
        # 4. Buscar empresa do usuário baseado no CNPJ
        # Normalizar CNPJ (remover formatação)
        cnpj_normalizado = request.cnpj.replace(".", "").replace("/", "").replace("-", "")
        
        empresa_response = db.table("empresas")\
            .select("id, razao_social")\
            .eq("usuario_id", current_user["id"])\
            .or_(f"cnpj.eq.{request.cnpj},cnpj.eq.{cnpj_normalizado}")\
            .execute()
        
        if not empresa_response.data or len(empresa_response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Empresa com CNPJ {request.cnpj} não encontrada. "
                    f"Cadastre a empresa primeiro."
                )
            )
        
        empresa = empresa_response.data[0]
        empresa_id = empresa["id"]
        
        logger.info(f"[EMPRESA] {empresa.get('razao_social')} | ID: {empresa_id}")
        
        # 5. Executar busca SEFAZ
        response = sefaz_service.buscar_notas_por_cnpj(
            cnpj=cnpj_normalizado,
            empresa_id=empresa_id,
            nsu_inicial=request.nsu_inicial,
        )
        
        # 6. Formatar resposta
        return {
            "success": response.sucesso,
            "status_codigo": response.status_codigo,
            "motivo": response.motivo,
            "plano": plano_info["nome"],
            "plano_limites": obter_resumo_plano(plano_info),
            "notas": [
                {
                    "chave_acesso": nota.chave_acesso,
                    "nsu": nota.nsu,
                    "data_emissao": nota.data_emissao.isoformat(),
                    "tipo_operacao": "saída" if nota.tipo_operacao == "1" else "entrada",
                    "valor_total": float(nota.valor_total),
                    "cnpj_emitente": nota.cnpj_emitente,
                    "nome_emitente": nota.nome_emitente,
                    "cnpj_destinatario": nota.cnpj_destinatario,
                    "cpf_destinatario": nota.cpf_destinatario,
                    "nome_destinatario": nota.nome_destinatario,
                    "situacao": nota.situacao,
                    "protocolo": nota.protocolo,
                }
                for nota in response.notas_encontradas
            ],
            "ultimo_nsu": response.ultimo_nsu,
            "max_nsu": response.max_nsu,
            "total_notas": response.total_notas,
            "tem_mais_notas": response.tem_mais_notas,
        }
        
    except SefazException as e:
        logger.error(f"Erro SEFAZ ao buscar notas: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "Erro ao comunicar com SEFAZ",
                "codigo": e.codigo,
                "mensagem": e.mensagem,
            }
        )
        
    except HTTPException:
        # Re-propagar exceções HTTP já formatadas
        raise
        
    except ValueError as e:
        logger.error(f"Erro de validação: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Dados inválidos", "mensagem": str(e)}
        )
        
    except Exception as e:
        logger.error(f"Erro inesperado ao buscar notas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Erro interno do servidor", "mensagem": str(e)}
        )


# ============================================
# ENDPOINT AUXILIAR - ESTATÍSTICAS
# ============================================

@router.get(
    "/buscar/stats/{cnpj}",
    summary="Estatísticas de notas por CNPJ",
    description="Retorna estatísticas de notas já buscadas para um CNPJ",
)
def obter_estatisticas_cnpj(
    cnpj: str,
    # current_user = Depends(get_current_user)
):
    """
    Retorna estatísticas de notas já consultadas.
    
    Útil para dashboards e visualização de dados.
    """
    # TODO: Implementar consulta ao banco de dados
    # count_total = db.query(NotaFiscal).filter_by(cnpj_emitente=cnpj).count()
    # sum_valores = db.query(func.sum(NotaFiscal.valor_total)).filter_by(...).scalar()
    
    return {
        "cnpj": cnpj,
        "total_notas": 0,
        "valor_total": 0.0,
        "ultimo_nsu_consultado": 0,
        "message": "Funcionalidade em desenvolvimento"
    }


# ============================================
# ENDPOINTS DE POLLING (BACKGROUND)
# ============================================

@router.post(
    "/buscar/iniciar",
    summary="Iniciar busca de notas em background",
    description="Inicia um Job de busca de notas distribuídas. Retorna o Job ID para monitoramento.",
)
async def iniciar_busca_background(
    request: ConsultaDistribuicaoRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Inicia busca assíncrona (Polling).
    """
    try:
        logger.info(f"[POLLING] Iniciando busca para CNPJ: {request.cnpj}")

        # 1. Verificar acesso ao módulo
        await verificar_acesso_modulo("buscador_notas", current_user, db)
        
        # 2. Obter plano do usuário
        plano_info = await obter_plano_usuario(current_user["id"], db)
        
        # 3. Validar limites
        await validar_limite_historico(plano_info, request.nsu_inicial)
        await validar_limite_consultas_dia(current_user["id"], plano_info, db)
        
        # Normalizar CNPJ (remover formatação)
        cnpj_normalizado = request.cnpj.replace(".", "").replace("/", "").replace("-", "")
        # Formatar CNPJ (XX.XXX.XXX/XXXX-XX)
        cnpj_formatado = f"{cnpj_normalizado[:2]}.{cnpj_normalizado[2:5]}.{cnpj_normalizado[5:8]}/{cnpj_normalizado[8:12]}-{cnpj_normalizado[12:]}"

        empresa_response = db.table("empresas")\
            .select("id")\
            .eq("usuario_id", current_user["id"])\
            .or_(f"cnpj.eq.{request.cnpj},cnpj.eq.{cnpj_normalizado},cnpj.eq.{cnpj_formatado}")\
            .execute()
        
        if not empresa_response.data:
            raise HTTPException(404, "Empresa não encontrada")
            
        empresa_id = empresa_response.data[0]["id"]
        
        # 5. Criar Job (PENDING)
        from datetime import datetime
        job_payload = {
            "user_id": current_user["id"],
            "type": "nfe_distribuicao",
            "status": "pending",
            # "created_at": "now()", # Deixar Supabase default
            # "updated_at": "now()"
        }
        
        # Nota: Usando db (admin) para criar job
        job_response = db.table("background_jobs").insert(job_payload).execute()
        
        if not job_response.data:
             raise HTTPException(500, "Erro ao criar job de busca")
             
        job_id = job_response.data[0]["id"]
        
        # 6. Despachar tarefa
        background_tasks.add_task(
            sefaz_service.executar_busca_assincrona,
            job_id=job_id,
            cnpj=cnpj_normalizado,
            empresa_id=empresa_id,
            nsu_inicial=request.nsu_inicial
        )
        
        return {
            "job_id": job_id,
            "status": "pending",
            "message": "Busca iniciada em segundo plano"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao iniciar busca background: {e}", exc_info=True)
        raise HTTPException(500, f"Erro interno: {str(e)}")


@router.get(
    "/buscar/status/{job_id}",
    summary="Verificar status da busca",
)
async def verificar_status_busca(
    job_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Verifica o status de um Job de busca.
    """
    try:
        # 1. Buscar Job
        response = db.table("background_jobs").select("*").eq("id", job_id).single().execute()
        
        if not response.data:
            raise HTTPException(404, "Job não encontrado")
            
        job = response.data
        
        # 2. Segurança: validar dono do job
        if job["user_id"] != current_user["id"]:
             raise HTTPException(403, "Acesso negado")
             
        return job

    except Exception as e:
        logger.error(f"Erro ao verificar status job {job_id}: {e}")
        raise HTTPException(500, "Erro ao verificar status")
