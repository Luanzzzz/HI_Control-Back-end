"""
Endpoints de busca e gestão de Notas Fiscais
"""
from typing import List
from fastapi import APIRouter, Depends, Query, Path, Response
from fastapi.responses import StreamingResponse
from supabase import Client
from datetime import datetime, date
from io import BytesIO

from app.dependencies import get_db, get_current_user, verificar_acesso_modulo
from app.models.nota_fiscal import (
    NotaFiscalResponse,
    NotaFiscalDetalhada,
    NotaFiscalSearchParams,
    BuscaNotaFilter
)
from app.services.busca_nf_service import busca_nf_service

router = APIRouter(tags=["Notas Fiscais"])


@router.get("/buscar", response_model=List[NotaFiscalResponse])
async def buscar_notas_avancado(
    tipo_nf: str = Query(None, description="Tipo de nota (NFe, NFSe, NFCe, CTe)"),
    cnpj_emitente: str = Query(None, min_length=14, max_length=18, description="CNPJ do emitente"),
    data_inicio: date = Query(..., description="Data inicial (obrigatório)"),
    data_fim: date = Query(..., description="Data final (obrigatório)"),
    numero_nf: str = Query(None, max_length=20, description="Número da nota"),
    serie: str = Query(None, max_length=10, description="Série da nota"),
    situacao: str = Query(None, description="Situação (autorizada, cancelada, denegada, processando)"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Busca avançada de notas fiscais com filtros específicos

    **Requer autenticação e módulo 'buscador_notas' no plano**

    **Filtros obrigatórios:**
    - `data_inicio` e `data_fim`: Período de busca (máximo 90 dias)

    **Filtros opcionais:**
    - `tipo_nf`: Tipo específico de nota
    - `cnpj_emitente`: CNPJ do emissor
    - `numero_nf`: Número exato da nota
    - `serie`: Série da nota
    - `situacao`: Situação atual da nota

    **Exemplos de uso:**
    ```
    GET /api/v1/notas/buscar?data_inicio=2024-01-01&data_fim=2024-01-31
    GET /api/v1/notas/buscar?data_inicio=2024-01-01&data_fim=2024-01-31&tipo_nf=NFe&situacao=autorizada
    GET /api/v1/notas/buscar?data_inicio=2024-01-15&data_fim=2024-01-31&cnpj_emitente=12.345.678/0001-90
    ```

    **Validações:**
    - Período máximo de 90 dias
    - CNPJ deve ser válido (formato e dígito verificador)
    - Datas não podem ser futuras

    Returns:
        Lista de notas fiscais encontradas
    """
    # Verificar acesso ao módulo
    await verificar_acesso_modulo("buscador_notas", usuario, db)

    # Construir filtro
    filtro = BuscaNotaFilter(
        tipo_nf=tipo_nf,
        cnpj_emitente=cnpj_emitente,
        data_inicio=data_inicio,
        data_fim=data_fim,
        numero_nf=numero_nf,
        serie=serie,
        situacao=situacao
    )

    # Buscar notas
    notas = await busca_nf_service.buscar_notas(filtro, usuario_id=usuario["id"])

    return notas


@router.get("/", response_model=List[NotaFiscalResponse])
async def buscar_notas(
    search_term: str = Query(None, description="Termo de busca (número, chave, CNPJ, nome)"),
    tipo_nf: str = Query("TODAS", description="Tipo de nota (NFe, NFSe, NFCe, CTe, TODAS)"),
    situacao: str = Query(None, description="Situação da nota"),
    data_inicio: datetime = Query(None, description="Data inicial (YYYY-MM-DD)"),
    data_fim: datetime = Query(None, description="Data final (YYYY-MM-DD)"),
    cnpj_emitente: str = Query(None, description="CNPJ do emitente"),
    skip: int = Query(0, ge=0, description="Paginação - offset"),
    limit: int = Query(100, ge=1, le=1000, description="Paginação - limite (máx 1000)"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Busca geral de notas fiscais com filtros flexíveis

    **Requer autenticação e módulo 'buscador_notas' no plano**

    **Filtros disponíveis:**
    - `search_term`: Busca geral por número, chave, CNPJ ou nome (case-insensitive)
    - `tipo_nf`: Filtrar por tipo específico ou TODAS
    - `situacao`: Filtrar por situação (autorizada, cancelada, denegada, processando)
    - `data_inicio` e `data_fim`: Filtrar por período de emissão
    - `cnpj_emitente`: Filtrar por CNPJ específico
    - `skip` e `limit`: Paginação dos resultados

    **Exemplos:**
    ```
    GET /api/v1/notas?tipo_nf=NFe&situacao=autorizada
    GET /api/v1/notas?search_term=Tech&limit=50
    GET /api/v1/notas?data_inicio=2024-01-01&data_fim=2024-01-31
    GET /api/v1/notas?cnpj_emitente=12.345.678/0001-90
    ```

    **Segurança:**
    - RLS (Row Level Security) garante que você vê apenas notas das suas empresas
    - Autenticação via JWT obrigatória

    Returns:
        Lista paginada de notas fiscais encontradas
    """
    # Verificar acesso ao módulo
    await verificar_acesso_modulo("buscador_notas", usuario, db)

    # Construir parâmetros
    params = NotaFiscalSearchParams(
        search_term=search_term,
        tipo_nf=tipo_nf,
        situacao=situacao,
        data_inicio=data_inicio,
        data_fim=data_fim,
        cnpj_emitente=cnpj_emitente,
        skip=skip,
        limit=limit
    )

    # Buscar notas
    notas = await busca_nf_service.buscar_notas_params(params, usuario_id=usuario["id"])

    return notas


@router.get("/{chave_acesso}", response_model=NotaFiscalDetalhada)
async def obter_nota_por_chave(
    chave_acesso: str = Path(..., min_length=44, max_length=44, description="Chave de acesso (44 dígitos)"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Obtém detalhes completos de uma nota fiscal pela chave de acesso

    **Requer autenticação e módulo 'buscador_notas' no plano**

    **Parâmetros:**
    - `chave_acesso`: Chave de acesso de 44 dígitos da NF-e/NFC-e/CT-e

    **Exemplo:**
    ```
    GET /api/v1/notas/35240112345678000190550010000001231000000001
    ```

    **Retorno incluí:**
    - Todos os campos básicos da nota
    - Valores de impostos (ICMS, IPI, PIS, COFINS)
    - Motivo de cancelamento (se aplicável)
    - Tags e categorização

    **Validações:**
    - Chave deve ter exatamente 44 dígitos numéricos
    - Dígito verificador deve ser válido
    - Nota deve pertencer a uma empresa vinculada ao usuário

    Returns:
        Detalhes completos da nota fiscal
    """
    # Verificar acesso ao módulo
    await verificar_acesso_modulo("buscador_notas", usuario, db)

    # Buscar detalhes
    nota = await busca_nf_service.obter_detalhes_nota(chave_acesso)

    return nota


@router.get("/{chave_acesso}/xml")
async def baixar_xml_nota(
    chave_acesso: str = Path(..., min_length=44, max_length=44, description="Chave de acesso (44 dígitos)"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Baixa o arquivo XML da nota fiscal

    **Requer autenticação e módulo 'buscador_notas' no plano**

    **Parâmetros:**
    - `chave_acesso`: Chave de acesso de 44 dígitos

    **Exemplo:**
    ```
    GET /api/v1/notas/35240112345678000190550010000001231000000001/xml
    ```

    **Resposta:**
    - Content-Type: application/xml
    - Content-Disposition: attachment; filename="NFe{chave}.xml"
    - Corpo: XML completo da nota fiscal

    **Nota:**
    - XML é baixado do Supabase Storage ou consultado diretamente na SEFAZ
    - Formato compatível com validadores e sistemas de gestão

    Returns:
        Arquivo XML da nota fiscal para download
    """
    # Verificar acesso ao módulo
    await verificar_acesso_modulo("buscador_notas", usuario, db)

    # Baixar XML
    xml_bytes = await busca_nf_service.baixar_xml(chave_acesso)

    # Criar response com XML
    return StreamingResponse(
        BytesIO(xml_bytes),
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=NFe{chave_acesso}.xml"
        }
    )


@router.get("/estatisticas/resumo")
async def obter_estatisticas_resumo(
    data_inicio: date = Query(..., description="Data inicial"),
    data_fim: date = Query(..., description="Data final"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """
    Obtém estatísticas resumidas das notas fiscais no período

    **Requer autenticação e módulo 'buscador_notas' no plano**

    **Parâmetros:**
    - `data_inicio` e `data_fim`: Período para cálculo das estatísticas

    **Exemplo:**
    ```
    GET /api/v1/notas/estatisticas/resumo?data_inicio=2024-01-01&data_fim=2024-01-31
    ```

    **Retorno:**
    - Total de notas no período
    - Valor total faturado
    - Quantidade por tipo (NFe, NFSe, NFCe, CTe)
    - Quantidade por situação
    - Média de valor por nota

    Returns:
        Estatísticas resumidas do período
    """
    # Verificar acesso ao módulo
    await verificar_acesso_modulo("buscador_notas", usuario, db)

    # Buscar todas as notas do período
    filtro = BuscaNotaFilter(
        data_inicio=data_inicio,
        data_fim=data_fim
    )
    notas = await busca_nf_service.buscar_notas(filtro, usuario_id=usuario["id"])

    # Calcular estatísticas
    total_notas = len(notas)
    valor_total = sum(nota.valor_total for nota in notas if nota.valor_total)

    # Contadores por tipo
    por_tipo = {}
    for nota in notas:
        tipo = nota.tipo_nf
        por_tipo[tipo] = por_tipo.get(tipo, 0) + 1

    # Contadores por situação
    por_situacao = {}
    for nota in notas:
        situacao = nota.situacao
        por_situacao[situacao] = por_situacao.get(situacao, 0) + 1

    # Média
    valor_medio = valor_total / total_notas if total_notas > 0 else 0

    return {
        "periodo": {
            "data_inicio": data_inicio.isoformat(),
            "data_fim": data_fim.isoformat()
        },
        "resumo": {
            "total_notas": total_notas,
            "valor_total": float(valor_total),
            "valor_medio": float(valor_medio)
        },
        "por_tipo": por_tipo,
        "por_situacao": por_situacao
    }
