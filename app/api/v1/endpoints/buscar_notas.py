"""
Endpoints REST para busca e importacao de notas fiscais.

A busca principal consulta o banco de dados local (Supabase).
Para popular o banco, use os endpoints de importacao de XML.

Fase 2 (futuro): DistribuicaoDFe para busca automatica no SEFAZ
(REQUER certificado digital A1).
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
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
from app.services.nfe_mapper import (
    extrair_numero_da_chave,
    extrair_serie_da_chave,
    extrair_modelo_da_chave,
    modelo_to_tipo_nf,
    gerar_id_from_chave
)
from app.services.plan_validation import (
    obter_plano_usuario,
    validar_limite_historico,
    validar_limite_consultas_dia,
    obter_resumo_plano
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfe", tags=["NFe - Busca"])


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def _enriquecer_nota(nota: NFeBuscadaMetadata) -> dict:
    """
    Helper para enriquecer nota com dados extraídos da chave de acesso.

    Args:
        nota: Metadata da nota fiscal buscada

    Returns:
        Dict com campos originais + campos extraídos da chave
    """
    try:
        numero_nf = extrair_numero_da_chave(nota.chave_acesso)
        serie = extrair_serie_da_chave(nota.chave_acesso)
        modelo = extrair_modelo_da_chave(nota.chave_acesso)
        tipo_nf = modelo_to_tipo_nf(modelo, nota.tipo_operacao)
        id_nota = gerar_id_from_chave(nota.chave_acesso)
    except (ValueError, IndexError) as e:
        logger.warning(f"⚠️ Erro ao extrair dados da chave {nota.chave_acesso}: {e}")
        # Fallback para valores padrão
        numero_nf = "N/A"
        serie = "N/A"
        tipo_nf = f"NFe {nota.tipo_operacao.capitalize()}"
        id_nota = nota.chave_acesso[-12:]

    return {
        # Campos originais
        "chave_acesso": nota.chave_acesso,
        "nsu": nota.nsu,
        "data_emissao": nota.data_emissao.isoformat(),
        "tipo_operacao": "saída" if nota.tipo_operacao == "1" else "entrada",
        "valor_total": float(nota.valor_total),
        "cnpj_emitente": nota.cnpj_emitente,
        "nome_emitente": nota.nome_emitente,
        "situacao": nota.situacao,

        # Campos extraídos
        "id": id_nota,
        "numero_nf": numero_nf,
        "serie": serie,
        "tipo_nf": tipo_nf,
    }


# ============================================
# ENDPOINT PRINCIPAL
# ============================================

@router.post(
    "/buscar",
    response_model=dict,
    summary="Buscar notas fiscais no banco de dados",
    description="""
    Busca notas fiscais cadastradas no banco de dados local.
    
    **Fonte de dados:** Banco de dados local (notas importadas via XML).
    Para popular o banco, use POST /importar-xml ou POST /importar-lote.
    
    **Limites por plano:**
    - Basico: Ultimos 30 dias, max 3 empresas
    - Premium: Ilimitado, max 10 empresas
    - Enterprise: Ilimitado, max 999 empresas
    
    **Retorna:**
    - Lista de notas encontradas com metadados
    - Total de notas
    - Orientacao para importacao quando banco vazio
    """,
)
async def buscar_notas_fiscais(
    request: ConsultaDistribuicaoRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Busca notas fiscais no banco de dados local.

    Este endpoint consulta APENAS o banco de dados local (Supabase).
    Para popular o banco com notas reais, use /importar-xml ou /importar-lote.

    Args:
        request: Dados da consulta (CNPJ, NSU/offset inicial, etc)
        current_user: Usuario autenticado
        db: Cliente Supabase admin

    Returns:
        Dict com lista de notas e orientacao de importacao quando vazio
    """
    try:
        logger.info(
            f"[BUSCA LOCAL] Usuario: {current_user.get('email')} | CNPJ: {request.cnpj}"
        )

        # 1. Verificar acesso ao modulo
        await verificar_acesso_modulo("buscador_notas", current_user, db)

        # 2. Obter plano do usuario
        plano_info = await obter_plano_usuario(current_user["id"], db)

        logger.info(
            f"[PLANO] {plano_info['nome'].upper()} | "
            f"Historico: {plano_info['limites']['historico_dias'] or 'ilimitado'} dias"
        )

        # 3. Validar limites do plano
        await validar_limite_historico(plano_info, request.nsu_inicial)
        await validar_limite_consultas_dia(current_user["id"], plano_info, db)

        # 4. Buscar empresa do usuario baseado no CNPJ
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
                    f"Empresa com CNPJ {request.cnpj} nao encontrada. "
                    f"Cadastre a empresa primeiro."
                )
            )

        empresa = empresa_response.data[0]
        empresa_id = empresa["id"]

        logger.info(f"[EMPRESA] {empresa.get('razao_social')} | ID: {empresa_id}")

        # 5. Executar busca no BANCO DE DADOS LOCAL (nao SEFAZ)
        response = sefaz_service.buscar_notas_por_cnpj(
            cnpj=cnpj_normalizado,
            empresa_id=empresa_id,
            nsu_inicial=request.nsu_inicial,
        )

        # 6. Aplicar limite de quantidade solicitado
        notas_limitadas = response.notas_encontradas[:request.max_notas]

        logger.info(
            f"[RESULTADO] Total encontradas: {len(response.notas_encontradas)} | "
            f"Limite aplicado: {request.max_notas} | "
            f"Retornando: {len(notas_limitadas)} notas"
        )

        # 7. Formatar resposta
        resultado = {
            "success": response.status_codigo == "138",
            "status_codigo": response.status_codigo,
            "motivo": response.motivo,
            "fonte": "banco_local",
            "plano": plano_info["nome"],
            "plano_limites": obter_resumo_plano(plano_info),
            "notas": [_enriquecer_nota(nota) for nota in notas_limitadas],
            "ultimo_nsu": response.ultimo_nsu,
            "max_nsu": response.max_nsu,
            "total_notas": len(notas_limitadas),
            "total_encontradas": response.total_notas,
            "tem_mais_notas": response.tem_mais_notas,
        }

        # 8. Quando banco vazio, adicionar orientacao de importacao
        if not notas_limitadas:
            resultado["mensagem"] = (
                "Nenhuma nota fiscal encontrada no periodo. "
                "Importe XMLs de notas fiscais usando o botao 'Importar XML' "
                "ou faca upload em lote atraves de 'Importar Lote (ZIP)'."
            )
            resultado["orientacao"] = {
                "titulo": "Como obter notas fiscais?",
                "passos": [
                    "1. Acesse o Portal da NF-e (www.nfe.fazenda.gov.br)",
                    "2. Baixe os XMLs das notas emitidas",
                    "3. Volte ao Hi-Control e importe os XMLs",
                    "4. As notas aparecerao automaticamente neste buscador"
                ],
                "endpoints_disponiveis": {
                    "importar_xml": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-xml",
                    "importar_lote": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-lote"
                }
            }

        return resultado

    except HTTPException:
        # Re-propagar excecoes HTTP ja formatadas
        raise

    except SefazException as e:
        # Safeguard: nao deveria mais ocorrer pois buscar_notas_por_cnpj
        # agora retorna lista vazia em vez de lancar excecao.
        logger.error(f"[SAFEGUARD] SefazException inesperada: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "Erro ao consultar banco de dados",
                "codigo": e.codigo,
                "mensagem": e.mensagem,
            }
        )

    except ValueError as e:
        logger.error(f"Erro de validacao: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Dados invalidos", "mensagem": str(e)}
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
    description="Retorna estatísticas de notas já importadas para um CNPJ",
)
async def obter_estatisticas_cnpj(
    cnpj: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Retorna estatísticas de notas já importadas no banco de dados.
    
    **Requer autenticação**
    
    **Nota:** Este endpoint consulta apenas o banco de dados local.
    As notas são importadas pelo bot automático ou via endpoints de importação.
    
    Args:
        cnpj: CNPJ do emitente (com ou sem formatação)
        
    Returns:
        {
            "success": true,
            "data": {
                "cnpj": "12345678000190",
                "total_notas": 150,
                "valor_total": 125000.50,
                "notas_por_tipo": {"NF-e": 100, "NFS-e": 50},
                "ultima_nota": "2026-02-10T14:30:00Z"
            }
        }
    """
    try:
        # Limpar CNPJ (remover formatação)
        import re
        cnpj_limpo = re.sub(r"[^0-9]", "", cnpj)
        
        if len(cnpj_limpo) != 14:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="CNPJ inválido. Deve conter 14 dígitos."
            )
        
        # Buscar todas as notas do CNPJ
        response = db.table("notas_fiscais")\
            .select("*")\
            .eq("emitente_cnpj", cnpj_limpo)\
            .execute()
        
        notas = response.data or []
        
        # Calcular estatísticas
        total_notas = len(notas)
        valor_total = sum(float(n.get("valor_total", 0)) for n in notas)
        
        # Notas por tipo
        notas_por_tipo: Dict[str, int] = {}
        for nota in notas:
            tipo = nota.get("tipo", "Desconhecido")
            notas_por_tipo[tipo] = notas_por_tipo.get(tipo, 0) + 1
        
        # Última nota (mais recente)
        ultima_nota = None
        if notas:
            # Ordenar por data_emissao ou created_at
            notas_ordenadas = sorted(
                notas,
                key=lambda x: x.get("data_emissao") or x.get("created_at") or "",
                reverse=True
            )
            ultima_nota = notas_ordenadas[0].get("data_emissao") or notas_ordenadas[0].get("created_at")
        
        return {
            "success": True,
            "data": {
                "cnpj": cnpj_limpo,
                "total_notas": total_notas,
                "valor_total": round(valor_total, 2),
                "notas_por_tipo": notas_por_tipo,
                "ultima_nota": ultima_nota
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter estatísticas para CNPJ {cnpj}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao obter estatísticas: {str(e)}"
        )


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


# ============================================
# ENDPOINTS POR EMPRESA (Sprint NFe Integration)
# ============================================

from app.services.cache_service import cache_service
from app.services.certificado_service import (
    certificado_service,
    CertificadoAusenteError,
    CertificadoExpiradoError,
    CertificadoError
)
from app.dependencies import verificar_acesso_empresa
from datetime import datetime, timedelta


@router.get(
    "/empresas/{empresa_id}/certificado/status",
    summary="Status do certificado de uma empresa",
    description="""
    Retorna o status do certificado digital da empresa.
    
    **Status possíveis:**
    - `ativo`: Certificado válido
    - `expirando`: Válido mas vence em menos de 30 dias
    - `vencido`: Certificado expirado
    - `ausente`: Empresa não possui certificado
    
    **Fallback:**
    Se a empresa não tiver certificado, verifica se o contador tem
    certificado válido que pode ser usado como fallback.
    """,
    tags=["NFe - Busca por Empresa"]
)
async def obter_status_certificado_empresa(
    empresa_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Retorna status do certificado de uma empresa.
    """
    try:
        # Validar acesso à empresa
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para acessar esta empresa"
            )
        
        # Obter status usando serviço híbrido
        status_cert = await certificado_service.validar_status_empresa(empresa_id)
        
        return {
            "empresa_id": empresa_id,
            **status_cert
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao verificar certificado empresa {empresa_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao verificar certificado: {str(e)}"
        )


@router.post(
    "/empresas/{empresa_id}/notas/buscar",
    summary="Buscar notas fiscais de uma empresa",
    description="""
    Busca notas fiscais no banco de dados local para uma empresa especifica.

    **Fonte de dados:** Banco de dados local (notas importadas via XML).
    Para popular o banco, use POST /importar-xml ou POST /importar-lote.

    **Cache:**
    - Resultados sao cacheados por 24 horas
    - Indica se dados vieram do cache ou banco

    **Certificado:**
    - Verifica status do certificado (informativo)
    - A busca no banco local NAO requer certificado
    - Certificado sera necessario na Fase 2 (DistribuicaoDFe)

    **Auditoria:**
    - Todas as consultas sao registradas no historico
    """,
    tags=["NFe - Busca por Empresa"]
)
async def buscar_notas_empresa(
    empresa_id: str,
    request: ConsultaDistribuicaoRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Busca notas no banco de dados local para uma empresa.

    IMPORTANTE: Este endpoint consulta APENAS o banco local.
    Ele NAO chama o SEFAZ diretamente. Para popular o banco,
    o usuario deve importar XMLs via /importar-xml ou /importar-lote.
    """
    inicio = datetime.now()
    filtros = request.model_dump() if hasattr(request, 'model_dump') else request.dict()

    try:
        # 1. Validar acesso a empresa
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar esta empresa"
            )

        # 2. Verificar modulo
        await verificar_acesso_modulo("buscador_notas", current_user, db)

        # 3. Verificar certificado (informativo - nao bloqueia busca no banco)
        status_cert = {"status": "nao_verificado", "mensagem": "Busca local nao requer certificado"}
        try:
            status_cert = await certificado_service.validar_status_empresa(empresa_id)
        except Exception as cert_err:
            logger.warning(f"Aviso: Nao foi possivel verificar certificado: {cert_err}")
            status_cert = {
                "status": "verificacao_indisponivel",
                "mensagem": f"Nao foi possivel verificar certificado: {str(cert_err)}"
            }

        # NOTA: Para busca no banco local, certificado NAO e obrigatorio.
        # O certificado sera necessario na Fase 2 (DistribuicaoDFe).
        # Por isso, nao bloqueamos a busca se certificado estiver ausente/vencido.

        # 4. Verificar cache
        chave_cache = cache_service.gerar_chave_cache(empresa_id, filtros)
        cache_hit = await cache_service.buscar(chave_cache)

        if cache_hit:
            # Registrar no historico (source: cache)
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            await _registrar_historico(
                db, empresa_id, current_user["id"], filtros,
                cache_hit.get("quantidade", 0), "cache", tempo_ms, True, None,
                "banco_local"
            )

            return {
                "success": True,
                "fonte": "cache",
                "cached_at": cache_hit["cached_at"],
                "empresa_id": empresa_id,
                "certificado_status": status_cert.get("status", "nao_verificado"),
                **cache_hit["dados"]
            }

        # 5. Buscar no BANCO DE DADOS LOCAL (nao SEFAZ)
        # NOTA: DistribuicaoDFe REQUER certificado digital A1.
        # (Contrario ao que se pensava anteriormente.)
        # Fase 2 implementara chamada real ao SEFAZ.
        cnpj = request.cnpj.replace(".", "").replace("/", "").replace("-", "")

        response = sefaz_service.buscar_notas_por_cnpj(
            cnpj=cnpj,
            empresa_id=empresa_id,
            nsu_inicial=request.nsu_inicial
        )

        # 6. Aplicar limite de quantidade solicitado
        notas_limitadas = response.notas_encontradas[:request.max_notas]

        logger.info(
            f"[RESULTADO EMPRESA] Encontradas: {len(response.notas_encontradas)} | "
            f"Limite: {request.max_notas} | Retornando: {len(notas_limitadas)}"
        )

        # 7. Formatar resultado
        resultado = {
            "notas": [_enriquecer_nota(nota) for nota in notas_limitadas],
            "ultimo_nsu": response.ultimo_nsu,
            "max_nsu": response.max_nsu,
            "total_notas": len(notas_limitadas),
            "total_encontradas": response.total_notas,
            "tem_mais_notas": response.tem_mais_notas,
        }

        # 8. Quando banco vazio, adicionar orientacao
        if not notas_limitadas:
            resultado["mensagem"] = (
                "Nenhuma nota fiscal encontrada no periodo. "
                "Importe XMLs de notas fiscais usando o botao 'Importar XML' "
                "ou faca upload em lote atraves de 'Importar Lote (ZIP)'."
            )
            resultado["orientacao"] = {
                "titulo": "Como obter notas fiscais?",
                "passos": [
                    "1. Acesse o Portal da NF-e (www.nfe.fazenda.gov.br)",
                    "2. Baixe os XMLs das notas emitidas",
                    "3. Volte ao Hi-Control e importe os XMLs",
                    "4. As notas aparecerao automaticamente neste buscador"
                ],
                "endpoints_disponiveis": {
                    "importar_xml": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-xml",
                    "importar_lote": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-lote"
                }
            }

        # 9. Salvar no cache (mesmo vazio, para evitar reprocessar)
        await cache_service.salvar(empresa_id, chave_cache, resultado)

        # 10. Registrar no historico
        tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
        await _registrar_historico(
            db, empresa_id, current_user["id"], filtros,
            response.total_notas, "banco_local", tempo_ms, True, None, "banco_local"
        )

        return {
            "success": True,
            "fonte": "banco_local",
            "empresa_id": empresa_id,
            "certificado_status": status_cert.get("status", "nao_verificado"),
            **resultado
        }

    except HTTPException:
        raise
    except SefazException as e:
        # Safeguard: nao deveria mais ocorrer pois buscar_notas_por_cnpj
        # agora retorna lista vazia em vez de lancar excecao.
        logger.error(f"[SAFEGUARD] SefazException inesperada em buscar_notas_empresa: {e}")
        tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
        await _registrar_historico(
            db, empresa_id, current_user["id"], filtros,
            0, "banco_local", tempo_ms, False, str(e), None
        )

        # Retornar 200 com lista vazia em vez de 502
        return {
            "success": False,
            "fonte": "banco_local",
            "empresa_id": empresa_id,
            "notas": [],
            "total_notas": 0,
            "total_encontradas": 0,
            "tem_mais_notas": False,
            "mensagem": (
                "Erro temporario ao consultar banco de dados. "
                "Tente novamente em alguns segundos."
            ),
            "erro_tecnico": str(e),
        }
    except Exception as e:
        logger.error(f"Erro ao buscar notas empresa {empresa_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "mensagem": str(e)}
        )


@router.get(
    "/empresas/{empresa_id}/notas/historico",
    summary="Histórico de consultas de uma empresa",
    description="Retorna o histórico de consultas SEFAZ para auditoria.",
    tags=["NFe - Busca por Empresa"]
)
async def obter_historico_empresa(
    empresa_id: str,
    limite: int = 50,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Retorna histórico de consultas para auditoria.
    """
    try:
        # Validar acesso
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para acessar esta empresa"
            )
        
        # Buscar histórico
        response = db.table("historico_consultas")\
            .select("*")\
            .eq("empresa_id", empresa_id)\
            .order("created_at", desc=True)\
            .limit(limite)\
            .execute()
        
        return {
            "empresa_id": empresa_id,
            "total": len(response.data) if response.data else 0,
            "historico": response.data or []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao buscar histórico empresa {empresa_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao buscar histórico: {str(e)}"
        )


async def _registrar_historico(
    db: Client,
    empresa_id: str,
    contador_id: str,
    filtros: dict,
    quantidade_notas: int,
    fonte: str,
    tempo_resposta_ms: int,
    sucesso: bool,
    erro_mensagem: str = None,
    certificado_tipo: str = None
):
    """
    Registra consulta no histórico para auditoria.
    """
    try:
        db.table("historico_consultas").insert({
            "empresa_id": empresa_id,
            "contador_id": contador_id,
            "filtros": filtros,
            "quantidade_notas": quantidade_notas,
            "fonte": fonte,
            "tempo_resposta_ms": tempo_resposta_ms,
            "sucesso": sucesso,
            "erro_mensagem": erro_mensagem,
            "certificado_tipo": certificado_tipo
        }).execute()
    except Exception as e:
        logger.warning(f"Erro ao registrar histórico: {e}")


# ============================================
# ENDPOINT: Download XML da Nota
# ============================================

@router.get("/notas/{chave_acesso}/xml")
async def baixar_xml_nota(
    chave_acesso: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Baixa o XML resumido (resNFe) da nota fiscal.

    O XML completo da nota pode ser obtido consultando diretamente
    a SEFAZ com certificado digital. Este endpoint retorna o resNFe
    (resumo) que foi retornado pela DistribuicaoDFe.

    Args:
        chave_acesso: Chave de acesso de 44 dígitos

    Returns:
        Response com XML para download

    Raises:
        404: XML não encontrado
        422: Chave de acesso inválida
    """
    from fastapi.responses import Response

    try:
        logger.info(f"📥 Download XML solicitado - Chave: {chave_acesso}")

        # 1. Validar chave de acesso
        if not chave_acesso or len(chave_acesso) != 44 or not chave_acesso.isdigit():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Chave de acesso inválida. Deve ter 44 dígitos numéricos."
            )

        # 2. Buscar nota no banco de dados
        try:
            resultado = db.table("notas_fiscais")\
                .select("xml_resumo, numero_nf, serie, tipo_nf, nome_emitente")\
                .eq("chave_acesso", chave_acesso)\
                .limit(1)\
                .execute()

            if not resultado.data or len(resultado.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Nota fiscal com chave {chave_acesso} não encontrada no banco de dados."
                )

            nota = resultado.data[0]

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Erro ao buscar nota no banco: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erro ao buscar nota: {str(e)}"
            )

        # 3. Validar se tem XML
        xml_content = nota.get("xml_resumo")
        if not xml_content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="XML não disponível para esta nota. Pode ter sido consultada antes da funcionalidade de armazenamento de XML."
            )

        # 4. Preparar nome do arquivo
        tipo = nota.get("tipo_nf", "NFe").replace(" ", "_")
        numero = nota.get("numero_nf", "000000")
        serie = nota.get("serie", "1")
        emitente = (nota.get("nome_emitente", "Nota") or "Nota").replace(" ", "_")[:30]

        filename = f"{tipo}_{numero}_Serie{serie}_{emitente}.xml"

        logger.info(f"✅ XML encontrado - Arquivo: {filename}")

        # 5. Retornar XML como arquivo para download
        return Response(
            content=xml_content.encode('utf-8') if isinstance(xml_content, str) else xml_content,
            media_type='application/xml',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'application/xml; charset=utf-8',
                'X-Content-Type-Options': 'nosniff'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Erro ao processar download de XML: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao processar XML: {str(e)}"
        )


# ============================================
# ENDPOINT: Limpar Cache de Teste
# ============================================

@router.post("/cache/limpar-teste", tags=["NFe - Cache"])
async def limpar_cache_teste(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Remove entradas de cache que contem dados de teste.

    Identifica e remove registros com:
    - "EMPRESA TESTE" no nome do emitente
    - CNPJ "12345678000190" (teste)

    Returns:
        Dict com quantidade de registros removidos
    """
    try:
        logger.info("Iniciando limpeza de cache de teste...")

        # Buscar todos os caches
        resultado = db.table("cache_notas_fiscais")\
            .select("id, dados")\
            .execute()

        if not resultado.data:
            return {"message": "Nenhum cache encontrado", "removidos": 0}

        ids_remover = []
        for entry in resultado.data:
            dados_str = str(entry.get("dados", ""))
            # Identificar dados de teste
            if "TESTE" in dados_str or "12345678000190" in dados_str:
                ids_remover.append(entry["id"])

        # Deletar caches de teste
        if ids_remover:
            db.table("cache_notas_fiscais")\
                .delete()\
                .in_("id", ids_remover)\
                .execute()

        logger.info(f"Cache de teste limpo: {len(ids_remover)} entradas removidas")

        return {
            "success": True,
            "message": f"{len(ids_remover)} entradas de cache de teste removidas",
            "removidos": len(ids_remover)
        }

    except Exception as e:
        logger.error(f"Erro ao limpar cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao limpar cache: {str(e)}"
        )


# ============================================
# ENDPOINT: Importar XML de Nota Fiscal
# ============================================

from fastapi import UploadFile, File
from typing import List


@router.post(
    "/empresas/{empresa_id}/notas/importar-xml",
    summary="Importar nota fiscal via XML",
    description="""
    Importa uma nota fiscal a partir de arquivo XML.

    **Formatos suportados:**
    - NF-e (modelo 55)
    - NFC-e (modelo 65)
    - Arquivo procNFe (NF-e com protocolo)

    **Como obter XMLs:**
    1. Portal Nacional da NF-e: https://www.nfe.fazenda.gov.br/portal
    2. Download individual de notas autorizadas
    3. Sistema contabil que exporta XMLs

    **Processo:**
    1. Valida estrutura do XML
    2. Extrai dados (chave, emitente, valores, etc)
    3. Persiste no banco de dados
    4. Retorna nota importada
    """,
    tags=["NFe - Importacao"]
)
async def importar_xml_nota(
    empresa_id: str,
    arquivo: UploadFile = File(..., description="Arquivo XML da nota fiscal"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Importa nota fiscal a partir de arquivo XML.
    """
    try:
        logger.info(f"Importando XML para empresa {empresa_id} - Arquivo: {arquivo.filename}")

        # 1. Validar acesso a empresa
        from app.dependencies import verificar_acesso_empresa
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar esta empresa"
            )

        # 2. Validar arquivo
        if not arquivo.filename.endswith('.xml'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Arquivo deve ser XML (.xml)"
            )

        # 3. Ler conteudo
        xml_content = await arquivo.read()

        if len(xml_content) > 5 * 1024 * 1024:  # 5MB max
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Arquivo muito grande. Maximo 5MB."
            )

        # 4. Importar usando servico
        from app.services.real_consulta_service import real_consulta_service

        nota_create, metadados = real_consulta_service.importar_xml(xml_content, empresa_id)

        # 5. Persistir no banco
        nota_dict = nota_create.model_dump() if hasattr(nota_create, 'model_dump') else nota_create.dict()

        # Converter Decimal para float para JSON
        for key, value in nota_dict.items():
            if hasattr(value, '__float__'):
                nota_dict[key] = float(value)

        # Adicionar XML completo
        nota_dict['xml_completo'] = metadados.get('xml_completo')

        # Upsert (insert ou update se ja existir)
        resultado = db.table("notas_fiscais")\
            .upsert(nota_dict, on_conflict="chave_acesso")\
            .execute()

        if not resultado.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao persistir nota no banco"
            )

        nota_salva = resultado.data[0]

        logger.info(f"XML importado com sucesso: {nota_create.chave_acesso}")

        return {
            "success": True,
            "message": "Nota fiscal importada com sucesso",
            "nota": {
                "id": nota_salva.get("id"),
                "chave_acesso": nota_create.chave_acesso,
                "numero_nf": nota_create.numero_nf,
                "serie": nota_create.serie,
                "tipo_nf": nota_create.tipo_nf,
                "data_emissao": nota_create.data_emissao.isoformat() if nota_create.data_emissao else None,
                "cnpj_emitente": nota_create.cnpj_emitente,
                "nome_emitente": nota_create.nome_emitente,
                "valor_total": float(nota_create.valor_total),
                "situacao": nota_create.situacao,
            }
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Erro de validacao ao importar XML: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"XML invalido: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Erro ao importar XML: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao importar XML: {str(e)}"
        )


@router.post(
    "/empresas/{empresa_id}/notas/importar-lote",
    summary="Importar lote de XMLs (ZIP)",
    description="""
    Importa multiplas notas fiscais de um arquivo ZIP contendo XMLs.

    **Formato esperado:**
    - Arquivo ZIP contendo arquivos .xml
    - Cada XML deve ser uma NF-e/NFC-e valida
    - Maximo 100 XMLs por lote
    - Maximo 50MB para o arquivo ZIP

    **Retorno:**
    - Lista de notas importadas com sucesso
    - Lista de erros para XMLs invalidos
    """,
    tags=["NFe - Importacao"]
)
async def importar_lote_xml(
    empresa_id: str,
    arquivo: UploadFile = File(..., description="Arquivo ZIP contendo XMLs"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Importa lote de XMLs via arquivo ZIP.
    """
    import zipfile
    import io

    try:
        logger.info(f"Importando lote ZIP para empresa {empresa_id}")

        # 1. Validar acesso
        from app.dependencies import verificar_acesso_empresa
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar esta empresa"
            )

        # 2. Validar arquivo
        if not arquivo.filename.endswith('.zip'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Arquivo deve ser ZIP (.zip)"
            )

        # 3. Ler conteudo
        zip_content = await arquivo.read()

        if len(zip_content) > 50 * 1024 * 1024:  # 50MB max
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Arquivo muito grande. Maximo 50MB."
            )

        # 4. Processar ZIP
        from app.services.real_consulta_service import real_consulta_service

        notas_importadas = []
        erros = []

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            xml_files = [f for f in zf.namelist() if f.endswith('.xml')]

            if len(xml_files) > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Maximo 100 XMLs por lote"
                )

            for xml_filename in xml_files:
                try:
                    xml_content = zf.read(xml_filename)
                    nota_create, metadados = real_consulta_service.importar_xml(xml_content, empresa_id)

                    # Persistir
                    nota_dict = nota_create.model_dump() if hasattr(nota_create, 'model_dump') else nota_create.dict()

                    for key, value in nota_dict.items():
                        if hasattr(value, '__float__'):
                            nota_dict[key] = float(value)

                    nota_dict['xml_completo'] = metadados.get('xml_completo')

                    resultado = db.table("notas_fiscais")\
                        .upsert(nota_dict, on_conflict="chave_acesso")\
                        .execute()

                    if resultado.data:
                        notas_importadas.append({
                            "arquivo": xml_filename,
                            "chave_acesso": nota_create.chave_acesso,
                            "numero_nf": nota_create.numero_nf,
                            "valor_total": float(nota_create.valor_total),
                        })

                except Exception as e:
                    erros.append({
                        "arquivo": xml_filename,
                        "erro": str(e)
                    })

        logger.info(f"Lote importado: {len(notas_importadas)} sucesso, {len(erros)} erros")

        return {
            "success": True,
            "message": f"Lote processado: {len(notas_importadas)} notas importadas",
            "total_arquivos": len(xml_files),
            "importadas": len(notas_importadas),
            "erros": len(erros),
            "notas": notas_importadas,
            "detalhes_erros": erros[:20]  # Limitar erros retornados
        }

    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo ZIP invalido ou corrompido"
        )
    except Exception as e:
        logger.error(f"Erro ao importar lote: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao importar lote: {str(e)}"
        )


# ============================================
# ENDPOINT: Buscar notas do BANCO (sem SEFAZ)
# ============================================

@router.get(
    "/empresas/{empresa_id}/notas",
    summary="Listar notas fiscais do banco de dados",
    description="""
    Lista notas fiscais cadastradas no banco de dados para uma empresa.

    **Fonte de dados:**
    - Notas importadas via XML
    - Notas consultadas anteriormente no SEFAZ

    **Filtros disponiveis:**
    - tipo_nf: NFE, NFCE, CTE, NFSE
    - situacao: autorizada, cancelada, denegada
    - data_inicio, data_fim: Periodo de emissao
    - search: Busca por numero, emitente ou chave
    """,
    tags=["NFe - Busca por Empresa"]
)
async def listar_notas_empresa(
    empresa_id: str,
    tipo_nf: Optional[str] = None,
    situacao: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Lista notas fiscais do banco de dados (sem consultar SEFAZ).
    """
    try:
        logger.info(f"Listando notas da empresa {empresa_id} do banco de dados")

        # 1. Validar acesso
        from app.dependencies import verificar_acesso_empresa
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar esta empresa"
            )

        # 2. Montar query
        query = db.table("notas_fiscais")\
            .select("*")\
            .eq("empresa_id", empresa_id)\
            .order("data_emissao", desc=True)

        # 3. Aplicar filtros
        if tipo_nf:
            query = query.eq("tipo_nf", tipo_nf.upper())

        if situacao:
            query = query.eq("situacao", situacao.lower())

        if data_inicio:
            query = query.gte("data_emissao", data_inicio)

        if data_fim:
            query = query.lte("data_emissao", data_fim)

        if search:
            query = query.or_(
                f"numero_nf.ilike.%{search}%,"
                f"nome_emitente.ilike.%{search}%,"
                f"chave_acesso.ilike.%{search}%"
            )

        # 4. Paginacao
        query = query.range(offset, offset + limit - 1)

        # 5. Executar
        resultado = query.execute()

        if not resultado.data:
            return {
                "success": True,
                "fonte": "banco_de_dados",
                "empresa_id": empresa_id,
                "total": 0,
                "notas": [],
                "message": "Nenhuma nota encontrada. Importe XMLs ou consulte o SEFAZ."
            }

        # 6. Formatar notas
        notas = []
        for row in resultado.data:
            nota = {
                "id": row.get("id"),
                "chave_acesso": row.get("chave_acesso", ""),
                "numero_nf": row.get("numero_nf", ""),
                "serie": row.get("serie", "1"),
                "tipo_nf": row.get("tipo_nf", "NFE"),
                "data_emissao": row.get("data_emissao"),
                "cnpj_emitente": row.get("cnpj_emitente", ""),
                "nome_emitente": row.get("nome_emitente", ""),
                "cnpj_destinatario": row.get("cnpj_destinatario"),
                "nome_destinatario": row.get("nome_destinatario"),
                "valor_total": float(row.get("valor_total", 0)),
                "situacao": row.get("situacao", "autorizada"),
                "tem_xml": bool(row.get("xml_completo") or row.get("xml_resumo")),
            }
            notas.append(nota)

        logger.info(f"Encontradas {len(notas)} notas no banco para empresa {empresa_id}")

        return {
            "success": True,
            "fonte": "banco_de_dados",
            "empresa_id": empresa_id,
            "total": len(notas),
            "limit": limit,
            "offset": offset,
            "notas": notas,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao listar notas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao listar notas: {str(e)}"
        )


# ============================================
# ENDPOINT: Consultar nota por chave no SEFAZ
# ============================================

@router.get(
    "/consultar-chave/{chave_acesso}",
    summary="Consultar nota por chave de acesso no SEFAZ",
    description="""
    Consulta uma NF-e especifica no SEFAZ usando a chave de acesso.

    **Requer certificado digital** - Usa NfeConsultaProtocolo.

    **Uso:**
    - Verificar status atual de uma nota
    - Obter protocolo de autorizacao
    - Confirmar se nota existe no SEFAZ

    **Alternativa sem certificado:**
    Use o endpoint /importar-xml com XML baixado do Portal NF-e.
    """,
    tags=["NFe - Consulta SEFAZ"]
)
async def consultar_nota_sefaz(
    chave_acesso: str,
    empresa_id: str = Query(..., description="ID da empresa"),
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Consulta nota no SEFAZ por chave de acesso.
    """
    try:
        logger.info(f"Consultando SEFAZ - Chave: {chave_acesso}")

        # 1. Validar chave
        if not chave_acesso or len(chave_acesso) != 44 or not chave_acesso.isdigit():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Chave de acesso invalida. Deve ter 44 digitos numericos."
            )

        # 2. Validar acesso
        from app.dependencies import verificar_acesso_empresa
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar esta empresa"
            )

        # 3. Verificar certificado
        from app.services.certificado_service import certificado_service

        status_cert = await certificado_service.validar_status_empresa(empresa_id)

        if status_cert["status"] in ["ausente", "vencido"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "certificado_indisponivel",
                    "mensagem": "Certificado digital necessario para consulta no SEFAZ. " +
                                "Alternativa: baixe o XML no Portal NF-e e use /importar-xml",
                    "portal_nfe": "https://www.nfe.fazenda.gov.br/portal"
                }
            )

        # 4. Obter certificado
        cert_data = await certificado_service.obter_certificado_empresa(empresa_id)

        if not cert_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nao foi possivel obter certificado da empresa"
            )

        # 5. Extrair UF da chave
        codigo_uf = chave_acesso[:2]
        uf_map = {
            "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
            "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
            "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
            "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
            "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
            "52": "GO", "53": "DF",
        }
        uf = uf_map.get(codigo_uf, "SP")

        # 6. Consultar SEFAZ usando endpoint 'consulta' (NfeConsultaProtocolo)
        response = sefaz_service.consultar_nfe(
            chave_acesso=chave_acesso,
            empresa_uf=uf,
            cert_bytes=cert_data.get('cert_bytes'),
            senha_cert=cert_data.get('senha')
        )

        # 7. Retornar resultado
        return {
            "success": True,
            "fonte": "sefaz",
            "chave_acesso": chave_acesso,
            "uf": uf,
            "status_codigo": response.status_codigo,
            "status_descricao": response.status_descricao,
            "protocolo": response.protocolo,
            "data_autorizacao": response.data_autorizacao if hasattr(response, 'data_autorizacao') else None,
        }

    except HTTPException:
        raise
    except SefazException as e:
        logger.error(f"Erro SEFAZ ao consultar chave: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "sefaz_error",
                "codigo": e.codigo,
                "mensagem": e.mensagem
            }
        )
    except Exception as e:
        logger.error(f"Erro ao consultar chave: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar SEFAZ: {str(e)}"
        )

