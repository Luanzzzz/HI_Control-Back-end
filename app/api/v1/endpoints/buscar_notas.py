"""
Endpoints REST para busca e importacao de notas fiscais.

A busca principal sincroniza notas novas na SEFAZ e consolida o resultado
no banco local da empresa antes de responder.

Os endpoints de importacao de XML continuam disponiveis como fallback manual
e para cargas historicas.
"""
import json
import logging
import re
import zipfile
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

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
from app.services.google_drive_service import google_drive_service

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
        # Usar apenas o tipo base (sem operação) para compatibilidade com o frontend
        tipo_nf_completo = modelo_to_tipo_nf(modelo, nota.tipo_operacao)
        tipo_nf = tipo_nf_completo.split(" ")[0]  # "NFe Entrada" → "NFe"
        id_nota = gerar_id_from_chave(nota.chave_acesso)
    except (ValueError, IndexError) as e:
        logger.warning(f"⚠️ Erro ao extrair dados da chave {nota.chave_acesso}: {e}")
        # Fallback para valores padrão
        numero_nf = "N/A"
        serie = "N/A"
        tipo_nf = "NFe"
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


async def _obter_ultima_sincronizacao_empresa(
    db: Client,
    empresa_id: str,
) -> Optional[str]:
    """Obtém a data da última nota importada para a empresa."""
    try:
        response = db.table("notas_fiscais")\
            .select("created_at")\
            .eq("empresa_id", empresa_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()

        if response.data:
            return response.data[0].get("created_at")
    except Exception as exc:
        logger.warning(
            "Não foi possível obter última sincronização da empresa %s: %s",
            empresa_id,
            exc,
        )

    return None


async def _montar_contexto_busca_hibrida(
    db: Client,
    empresa_id: str,
    possui_notas_locais: bool,
    sincronizacao_disponivel: bool = False,
    acao_sugerida: Optional[str] = None,
    sincronizacao_pendente: Optional[bool] = None,
) -> Dict[str, object]:
    """Monta metadados estáveis para o front do fluxo híbrido."""
    return {
        "modo_busca": "hibrido",
        "tem_dados_locais": possui_notas_locais,
        "sincronizacao_disponivel": sincronizacao_disponivel,
        "sincronizacao_pendente": (
            sincronizacao_pendente
            if sincronizacao_pendente is not None
            else (sincronizacao_disponivel and not possui_notas_locais)
        ),
        "acao_sugerida": acao_sugerida,
        "ultima_sincronizacao": await _obter_ultima_sincronizacao_empresa(db, empresa_id),
    }


class ExportacaoXmlLoteRequest(BaseModel):
    """Payload para exportacao em lote dos XMLs do buscador."""

    cnpj: str = Field(..., min_length=14, max_length=18)
    sincronizar_antes: bool = True


def _normalizar_cnpj_busca(cnpj: str) -> str:
    """Remove formatacao do CNPJ recebido nas rotas do buscador."""
    return re.sub(r"\D", "", cnpj or "")


def _sanitizar_nome_arquivo(valor: Optional[str], fallback: str) -> str:
    """Produz nome de arquivo seguro para ZIP e downloads."""
    valor_limpo = re.sub(r"[^\w\-]+", "_", (valor or "").strip(), flags=re.UNICODE)
    valor_limpo = valor_limpo.strip("_")
    return (valor_limpo or fallback)[:80]


def _montar_nome_xml_lote(nota: Dict[str, Any]) -> str:
    """Gera nome consistente para o XML exportado em lote."""
    tipo_nf = _sanitizar_nome_arquivo(str(nota.get("tipo_nf") or "NFe"), "NFe")
    numero = _sanitizar_nome_arquivo(str(nota.get("numero_nf") or "sem_numero"), "sem_numero")
    serie = _sanitizar_nome_arquivo(str(nota.get("serie") or "1"), "1")
    emitente = _sanitizar_nome_arquivo(str(nota.get("nome_emitente") or "emitente"), "emitente")
    chave = _sanitizar_nome_arquivo(str(nota.get("chave_acesso") or nota.get("id") or "sem_chave"), "sem_chave")
    return f"{tipo_nf}_{numero}_Serie{serie}_{emitente}_{chave}.xml"


async def _sincronizar_busca_empresa_para_lote(
    empresa_id: str,
    cnpj: str,
    current_user: dict,
) -> Dict[str, Any]:
    """Sincroniza a empresa antes da exportacao, quando solicitado."""
    cnpj_normalizado = _normalizar_cnpj_busca(cnpj)
    if len(cnpj_normalizado) != 14:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CNPJ invalido. Deve conter 14 digitos numericos.",
        )

    return await sefaz_service.sincronizar_e_buscar_notas_por_cnpj(
        cnpj=cnpj_normalizado,
        empresa_id=empresa_id,
        contador_id=current_user["id"],
        nsu_inicial=0,
        max_notas=200,
    )


async def _listar_notas_empresa_para_exportacao(
    db: Client,
    empresa_id: str,
    page_size: int = 500,
) -> List[Dict[str, Any]]:
    """
    Lista todas as NF-es/NFC-es da empresa, paginando o banco local.

    O objetivo aqui e garantir cobertura do historico inteiro ja persistido,
    nao apenas da pagina atualmente exibida no front.
    """
    notas: List[Dict[str, Any]] = []
    offset = 0

    while True:
        resultado = (
            db.table("notas_fiscais")
            .select(
                "id, chave_acesso, numero_nf, serie, tipo_nf, tipo_operacao, "
                "data_emissao, nome_emitente, valor_total, xml_completo, xml_resumo"
            )
            .eq("empresa_id", empresa_id)
            .in_("tipo_nf", ["NFe", "NFCe"])
            .order("data_emissao", desc=True)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        lote = resultado.data or []
        if not lote:
            break

        notas.extend(lote)
        if len(lote) < page_size:
            break

        offset += page_size

    return notas


def _filtrar_notas_com_xml(notas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mantem apenas notas com chave fiscal valida e XML disponivel."""
    filtradas: List[Dict[str, Any]] = []

    for nota in notas:
        chave_acesso = str(nota.get("chave_acesso") or "").strip()
        xml_content = nota.get("xml_completo") or nota.get("xml_resumo")

        if not chave_acesso.isdigit() or len(chave_acesso) != 44:
            continue
        if not xml_content:
            continue

        filtradas.append(nota)

    return filtradas


def _gerar_zip_xmls(notas: List[Dict[str, Any]], empresa_id: str) -> bytes:
    """Gera ZIP com todos os XMLs exportaveis da empresa."""
    buffer = BytesIO()
    nomes_utilizados: Dict[str, int] = {}

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        resumo = {
            "empresa_id": empresa_id,
            "gerado_em": datetime.now().isoformat(),
            "total_xmls": len(notas),
            "arquivos": [],
        }

        for nota in notas:
            nome_base = _montar_nome_xml_lote(nota)
            contador = nomes_utilizados.get(nome_base, 0)
            nomes_utilizados[nome_base] = contador + 1
            nome_arquivo = (
                nome_base
                if contador == 0
                else nome_base.replace(".xml", f"_{contador + 1}.xml")
            )

            xml_content = nota.get("xml_completo") or nota.get("xml_resumo") or ""
            xml_bytes = (
                xml_content.encode("utf-8")
                if isinstance(xml_content, str)
                else xml_content
            )

            zip_file.writestr(nome_arquivo, xml_bytes)
            resumo["arquivos"].append(
                {
                    "arquivo": nome_arquivo,
                    "chave_acesso": nota.get("chave_acesso"),
                    "numero_nf": nota.get("numero_nf"),
                    "serie": nota.get("serie"),
                }
            )

        zip_file.writestr(
            "resumo_exportacao.json",
            json.dumps(resumo, ensure_ascii=False, indent=2).encode("utf-8"),
        )

    buffer.seek(0)
    return buffer.getvalue()


# ============================================
# ENDPOINT PRINCIPAL
# ============================================

@router.post(
    "/buscar",
    response_model=dict,
    summary="Buscar notas fiscais no banco de dados",
    description="""
    Sincroniza notas novas na SEFAZ e retorna o consolidado da empresa.
    
    **Fonte de dados:** Consulta automatica SEFAZ + historico local.
    Para cargas manuais, use POST /importar-xml ou POST /importar-lote.
    
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
    Busca notas fiscais da empresa com sincronizacao automatica na SEFAZ.

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
        plano_info = await obter_plano_usuario(
            current_user["id"], db, is_admin=bool(current_user.get("is_admin"))
        )

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
            .select("id, razao_social, usuario_id")\
            .eq("usuario_id", current_user["id"])\
            .eq("ativa", True)\
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

        # Validacao multi-tenancy: assegurar que empresa pertence ao usuario
        if empresa.get("usuario_id") != current_user["id"]:
            logger.warning(
                f"[SECURITY] Tentativa de acesso não autorizado a empresa {empresa_id} "
                f"por usuario {current_user['id']}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado a esta empresa"
            )

        logger.info(f"[EMPRESA] {empresa.get('razao_social')} | ID: {empresa_id}")

        # 5. Fluxo principal: sincronizar notas novas na SEFAZ e depois
        # montar a resposta com historico + notas recem-importadas.
        busca_resultado = await sefaz_service.sincronizar_e_buscar_notas_por_cnpj(
            cnpj=cnpj_normalizado,
            empresa_id=empresa_id,
            contador_id=current_user["id"],
            nsu_inicial=request.nsu_inicial,
            max_notas=request.max_notas,
        )
        response = busca_resultado["response"]
        consulta_inicial = request.nsu_inicial in (None, 0)

        # 6. Aplicar limite de quantidade solicitado
        notas_limitadas = response.notas_encontradas[:request.max_notas]

        logger.info(
            f"[RESULTADO] Total encontradas: {len(response.notas_encontradas)} | "
            f"Limite aplicado: {request.max_notas} | "
            f"Retornando: {len(notas_limitadas)} notas"
        )

        # 7. Formatar resposta
        resultado = {
            "success": (
                bool(notas_limitadas)
                or not consulta_inicial
                or bool(busca_resultado["sincronizacao_realizada"])
            ),
            "status_codigo": response.status_codigo,
            "motivo": response.motivo,
            "fonte": busca_resultado["fonte"],
            "plano": plano_info["nome"],
            "plano_limites": obter_resumo_plano(plano_info),
            "certificado_usado": busca_resultado["certificado_usado"],
            "sincronizacao_automatica": busca_resultado["sincronizacao_realizada"],
            "novas_notas_sincronizadas": busca_resultado["novas_notas_sincronizadas"],
            "notas": [_enriquecer_nota(nota) for nota in notas_limitadas],
            "ultimo_nsu": response.ultimo_nsu,
            "max_nsu": response.max_nsu,
            "total_notas": len(notas_limitadas),
            "total_encontradas": response.total_notas,
            "tem_mais_notas": response.tem_mais_notas,
        }

        resultado.update(
            await _montar_contexto_busca_hibrida(
                db,
                empresa_id,
                bool(notas_limitadas),
                sincronizacao_disponivel=(
                    not busca_resultado["sincronizacao_realizada"]
                    and not notas_limitadas
                ),
                acao_sugerida=(
                    "solicitar_sincronizacao_bot"
                    if not busca_resultado["sincronizacao_realizada"] and not notas_limitadas
                    else None
                ),
            )
        )

        # 8. Quando nao houver notas, explicar o que ocorreu no fluxo automatico
        if not notas_limitadas:
            if busca_resultado["sincronizacao_realizada"]:
                resultado["mensagem"] = (
                    "Nenhuma nota foi encontrada apos a consulta automatica na SEFAZ "
                    "e a verificacao do historico local."
                )
            else:
                resultado["mensagem"] = (
                    busca_resultado["mensagem_sincronizacao"]
                    or "Nao foi possivel sincronizar novas notas na SEFAZ. "
                    "O resultado abaixo reflete apenas o banco local."
                )

            resultado["orientacao"] = {
                "titulo": "Como recuperar notas nesta busca?",
                "passos": [
                    "1. Verifique se a empresa possui certificado digital valido para consulta automatica",
                    "2. Se o certificado estiver indisponivel, solicite uma sincronizacao assistida ou importe XMLs manualmente",
                    "3. Aguarde o processamento da sincronizacao",
                    "4. Execute a busca novamente neste modulo"
                ],
                "acoes_sugeridas": [
                    "solicitar_sincronizacao_bot",
                    "importar_xml_manual"
                ],
                "endpoints_disponiveis": {
                    "sincronizar_bot": "/api/v1/bot/sincronizar-agora",
                    "importar_xml": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-xml",
                    "importar_lote": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-lote"
                }
            }

        if busca_resultado["mensagem_sincronizacao"] and notas_limitadas:
            resultado["mensagem"] = busca_resultado["mensagem_sincronizacao"]

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
        
        empresas_response = db.table("empresas")\
            .select("id, cnpj")\
            .eq("usuario_id", usuario["id"])\
            .eq("ativa", True)\
            .execute()

        empresas = empresas_response.data or []

        empresa = next(
            (
                item for item in empresas
                if re.sub(r"[^0-9]", "", str(item.get("cnpj", ""))) == cnpj_limpo
            ),
            None
        )

        if not empresa:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada"
            )

        # Buscar todas as notas da empresa do usuário
        response = db.table("notas_fiscais")\
            .select("*")\
            .eq("empresa_id", empresa["id"])\
            .execute()
        
        notas = response.data or []
        
        # Calcular estatísticas
        total_notas = len(notas)
        valor_total = sum(float(n.get("valor_total", 0)) for n in notas)
        
        # Notas por tipo
        notas_por_tipo: Dict[str, int] = {}
        for nota in notas:
            tipo = nota.get("tipo_nf") or nota.get("tipo") or "Desconhecido"
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
        plano_info = await obter_plano_usuario(
            current_user["id"], db, is_admin=bool(current_user.get("is_admin"))
        )

        # 3. Validar limites
        await validar_limite_historico(plano_info, request.nsu_inicial)
        await validar_limite_consultas_dia(current_user["id"], plano_info, db)
        
        # Normalizar CNPJ (remover formatação)
        cnpj_normalizado = request.cnpj.replace(".", "").replace("/", "").replace("-", "")
        # Formatar CNPJ (XX.XXX.XXX/XXXX-XX)
        cnpj_formatado = f"{cnpj_normalizado[:2]}.{cnpj_normalizado[2:5]}.{cnpj_normalizado[5:8]}/{cnpj_normalizado[8:12]}-{cnpj_normalizado[12:]}"

        empresa_response = db.table("empresas")\
            .select("id, usuario_id")\
            .eq("usuario_id", current_user["id"])\
            .eq("ativa", True)\
            .or_(f"cnpj.eq.{request.cnpj},cnpj.eq.{cnpj_normalizado},cnpj.eq.{cnpj_formatado}")\
            .execute()
        
        if not empresa_response.data:
            raise HTTPException(404, "Empresa não encontrada")

        empresa = empresa_response.data[0]
        empresa_id = empresa["id"]

        # Validacao multi-tenancy: assegurar que empresa pertence ao usuario
        if empresa.get("usuario_id") != current_user["id"]:
            logger.warning(
                f"[SECURITY] Tentativa de acesso não autorizado a empresa {empresa_id} "
                f"por usuario {current_user['id']}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado a esta empresa"
            )
        
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
    Busca notas da empresa sincronizando primeiro com a SEFAZ quando aplicavel.
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

        # 4. Fluxo oficial: sincronizar primeiro com a SEFAZ e depois
        # consultar o banco local consolidado. Nao usamos cache de leitura
        # aqui para nao esconder notas novas recem-disponibilizadas.
        cnpj = request.cnpj.replace(".", "").replace("/", "").replace("-", "")

        busca_resultado = await sefaz_service.sincronizar_e_buscar_notas_por_cnpj(
            cnpj=cnpj,
            empresa_id=empresa_id,
            contador_id=current_user["id"],
            nsu_inicial=request.nsu_inicial,
            max_notas=request.max_notas,
        )
        response = busca_resultado["response"]
        consulta_inicial = request.nsu_inicial in (None, 0)

        if consulta_inicial:
            await cache_service.invalidar(empresa_id=empresa_id)

        # 5. Aplicar limite de quantidade solicitado
        notas_limitadas = response.notas_encontradas[:request.max_notas]

        logger.info(
            f"[RESULTADO EMPRESA] Encontradas: {len(response.notas_encontradas)} | "
            f"Limite: {request.max_notas} | Retornando: {len(notas_limitadas)}"
        )

        # 6. Formatar resultado
        resultado = {
            "success": (
                bool(notas_limitadas)
                or not consulta_inicial
                or bool(busca_resultado["sincronizacao_realizada"])
            ),
            "fonte": busca_resultado["fonte"],
            "certificado_usado": busca_resultado["certificado_usado"],
            "sincronizacao_automatica": busca_resultado["sincronizacao_realizada"],
            "novas_notas_sincronizadas": busca_resultado["novas_notas_sincronizadas"],
            "notas": [_enriquecer_nota(nota) for nota in notas_limitadas],
            "ultimo_nsu": response.ultimo_nsu,
            "max_nsu": response.max_nsu,
            "total_notas": len(notas_limitadas),
            "total_encontradas": response.total_notas,
            "tem_mais_notas": response.tem_mais_notas,
        }

        contexto_hibrido = await _montar_contexto_busca_hibrida(
            db,
            empresa_id,
            bool(notas_limitadas),
            sincronizacao_disponivel=(
                not busca_resultado["sincronizacao_realizada"]
                and not notas_limitadas
            ),
            acao_sugerida=(
                "solicitar_sincronizacao_bot"
                if not busca_resultado["sincronizacao_realizada"] and not notas_limitadas
                else None
            ),
        )
        resultado.update(contexto_hibrido)

        # 7. Quando nao houver notas, explicar o resultado da busca automatica
        if not notas_limitadas:
            if busca_resultado["sincronizacao_realizada"]:
                resultado["mensagem"] = (
                    "Nenhuma nota foi encontrada apos a consulta automatica na SEFAZ "
                    "e a verificacao do historico local desta empresa."
                )
            else:
                resultado["mensagem"] = (
                    busca_resultado["mensagem_sincronizacao"]
                    or "Nao foi possivel consultar novas notas na SEFAZ. "
                    "O retorno abaixo reflete apenas o banco local."
                )

            resultado["orientacao"] = {
                "titulo": "Como recuperar notas nesta busca?",
                "passos": [
                    "1. Verifique se o certificado digital da empresa esta valido",
                    "2. Se a consulta automatica estiver indisponivel, solicite sincronizacao assistida ou importe XMLs",
                    "3. Aguarde a sincronizacao/processamento",
                    "4. Execute a busca novamente neste modulo"
                ],
                "acoes_sugeridas": [
                    "solicitar_sincronizacao_bot",
                    "importar_xml_manual"
                ],
                "endpoints_disponiveis": {
                    "sincronizar_bot": "/api/v1/bot/sincronizar-agora",
                    "importar_xml": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-xml",
                    "importar_lote": f"/api/v1/nfe/empresas/{empresa_id}/notas/importar-lote"
                }
            }

        if busca_resultado["mensagem_sincronizacao"] and notas_limitadas:
            resultado["mensagem"] = busca_resultado["mensagem_sincronizacao"]

        # 8. Registrar no historico
        tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
        await _registrar_historico(
            db, empresa_id, current_user["id"], filtros,
            response.total_notas,
            busca_resultado["fonte"],
            tempo_ms,
            bool(resultado["success"]),
            None if resultado["success"] else busca_resultado["mensagem_sincronizacao"],
            busca_resultado["certificado_usado"],
        )

        return {
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
            "certificado_status": "indisponivel",
            "certificado_usado": "indisponivel",
            **(await _montar_contexto_busca_hibrida(db, empresa_id, False)),
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
# ENDPOINTS: EXPORTACAO DE XMLS EM LOTE
# ============================================

@router.post(
    "/empresas/{empresa_id}/notas/xmls/lote/baixar",
    summary="Baixar XMLs em lote da empresa",
    tags=["NFe - Exportacao"],
)
async def baixar_xmls_lote_empresa(
    empresa_id: str,
    request: ExportacaoXmlLoteRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Gera um ZIP com todos os XMLs fiscais (NFe/NFCe) ja persistidos para a empresa.

    Antes da exportacao, opcionalmente sincroniza com a SEFAZ para incluir notas novas.
    """
    try:
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar esta empresa",
            )

        await verificar_acesso_modulo("buscador_notas", current_user, db)

        sync_result: Optional[Dict[str, Any]] = None
        if request.sincronizar_antes:
            sync_result = await _sincronizar_busca_empresa_para_lote(
                empresa_id=empresa_id,
                cnpj=request.cnpj,
                current_user=current_user,
            )

        notas = await _listar_notas_empresa_para_exportacao(db, empresa_id)
        notas_com_xml = _filtrar_notas_com_xml(notas)

        if not notas_com_xml:
            mensagem_sync = sync_result["mensagem_sincronizacao"] if sync_result else None
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    mensagem_sync
                    or "Nenhum XML fiscal disponivel para exportacao nesta empresa."
                ),
            )

        zip_bytes = _gerar_zip_xmls(notas_com_xml, empresa_id)
        filename = f"xmls_empresa_{empresa_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

        return StreamingResponse(
            BytesIO(zip_bytes),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Total-XMLs": str(len(notas_com_xml)),
                "X-Total-Notas": str(len(notas)),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro ao gerar lote de XMLs da empresa %s: %s", empresa_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao exportar XMLs em lote: {str(e)}",
        )


@router.post(
    "/empresas/{empresa_id}/notas/xmls/lote/salvar-drive",
    summary="Salvar XMLs em lote no Google Drive",
    tags=["NFe - Exportacao"],
)
async def salvar_xmls_lote_drive(
    empresa_id: str,
    request: ExportacaoXmlLoteRequest,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Salva todos os XMLs fiscais (NFe/NFCe) da empresa no Google Drive configurado.
    """
    try:
        if not await verificar_acesso_empresa(current_user["id"], empresa_id, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Voce nao tem permissao para acessar esta empresa",
            )

        await verificar_acesso_modulo("buscador_notas", current_user, db)

        sync_result: Optional[Dict[str, Any]] = None
        if request.sincronizar_antes:
            sync_result = await _sincronizar_busca_empresa_para_lote(
                empresa_id=empresa_id,
                cnpj=request.cnpj,
                current_user=current_user,
            )

        empresa_result = (
            db.table("empresas")
            .select("id, razao_social")
            .eq("id", empresa_id)
            .limit(1)
            .execute()
        )
        empresa = (empresa_result.data or [{}])[0]
        empresa_nome = empresa.get("razao_social") or f"empresa_{empresa_id}"

        notas = await _listar_notas_empresa_para_exportacao(db, empresa_id)
        notas_com_xml = _filtrar_notas_com_xml(notas)

        if not notas_com_xml:
            mensagem_sync = sync_result["mensagem_sincronizacao"] if sync_result else None
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    mensagem_sync
                    or "Nenhum XML fiscal disponivel para salvar no Drive."
                ),
            )

        resultado_drive = await google_drive_service.salvar_xmls_lote_no_drive(
            empresa_id=empresa_id,
            empresa_nome=empresa_nome,
            notas=notas_com_xml,
        )

        return {
            "success": True,
            "empresa_id": empresa_id,
            "total_notas_consideradas": len(notas),
            "total_xmls_processados": len(notas_com_xml),
            "sincronizacao_automatica": bool(sync_result and sync_result.get("sincronizacao_realizada")),
            "novas_notas_sincronizadas": int((sync_result or {}).get("novas_notas_sincronizadas") or 0),
            **resultado_drive,
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("Erro ao salvar lote de XMLs no Drive da empresa %s: %s", empresa_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao salvar XMLs no Drive: {str(e)}",
        )


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
                .select("xml_resumo, xml_completo, numero_nf, serie, tipo_nf, nome_emitente")\
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
        xml_content = nota.get("xml_completo") or nota.get("xml_resumo")
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
            # Normalizar tipo_nf: aceitar "NFE", "nfe", "NFe" → "NFe"
            tipo_map = {"NFE": "NFe", "NFCE": "NFCe", "CTE": "CTe", "NFSE": "NFSe"}
            tipo_nf_norm = tipo_map.get(tipo_nf.upper(), tipo_nf)
            query = query.eq("tipo_nf", tipo_nf_norm)

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

