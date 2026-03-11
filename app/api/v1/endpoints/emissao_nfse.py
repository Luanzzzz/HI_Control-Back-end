"""
Endpoints para emissão e cancelamento de NFS-e.

Funcionalidades:
- Emitir NFS-e via APIs municipais (padrão ABRASF)
- Cancelar NFS-e emitida
- Listar municípios suportados para emissão
- Consultar resultado de lote de RPS
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from supabase import Client
from decimal import Decimal
import logging

from app.dependencies import get_db, get_current_user, require_modules
from app.services.nfse.emissao_nfse_service import (
    emissao_nfse_service,
    MUNICIPIOS_EXPANDIDOS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfse/emissao", tags=["NFS-e - Emissão"])


# ============================================
# SCHEMAS
# ============================================

class NFSeTomadorCreate(BaseModel):
    cnpj: Optional[str] = None
    cpf: Optional[str] = None
    nome: str = Field(..., max_length=100)
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    codigo_municipio: Optional[str] = None
    uf: Optional[str] = None
    cep: Optional[str] = None
    email: Optional[str] = None


class NFSeServicoCreate(BaseModel):
    item_lista: str = Field(
        ..., description="Código do item na lista de serviços LC 116"
    )
    cnae: Optional[str] = Field(None, description="Código CNAE")
    discriminacao: str = Field(
        ..., max_length=2000, description="Descrição detalhada do serviço"
    )


class NFSeEmissaoCreate(BaseModel):
    """Dados para emissão de NFS-e."""
    empresa_id: str
    numero_rps: Optional[str] = Field(
        None, description="Número do RPS (auto se vazio)"
    )
    serie_rps: str = Field(default="RPS", max_length=5)

    tomador: NFSeTomadorCreate
    servico: NFSeServicoCreate

    valor_servicos: Decimal = Field(..., gt=0)
    valor_deducoes: Decimal = Field(default=Decimal("0"))
    valor_pis: Decimal = Field(default=Decimal("0"))
    valor_cofins: Decimal = Field(default=Decimal("0"))
    valor_inss: Decimal = Field(default=Decimal("0"))
    valor_ir: Decimal = Field(default=Decimal("0"))
    valor_csll: Decimal = Field(default=Decimal("0"))
    iss_retido: str = Field(
        default="2", description="1=Sim, 2=Não"
    )
    aliquota_iss: Decimal = Field(default=Decimal("0"))
    valor_iss: Decimal = Field(default=Decimal("0"))
    simples_nacional: str = Field(
        default="2", description="1=Sim, 2=Não"
    )


class NFSeEmissaoResponse(BaseModel):
    sucesso: bool
    numero_nfse: Optional[str] = None
    codigo_verificacao: Optional[str] = None
    protocolo_lote: Optional[str] = None
    data_emissao: Optional[str] = None
    nota_id: Optional[str] = None
    mensagem: Optional[str] = None
    erro: Optional[str] = None
    correcao: Optional[str] = None


class NFSeCancelamentoResponse(BaseModel):
    sucesso: bool
    mensagem: Optional[str] = None
    erro: Optional[str] = None


class MunicipioSuportado(BaseModel):
    codigo_ibge: str
    nome: str
    uf: str
    sistema: str
    status: str


# ============================================
# EMISSÃO
# ============================================

@router.post(
    "/emitir",
    response_model=NFSeEmissaoResponse,
    dependencies=[require_modules("emissor_notas")],
    status_code=201,
    summary="Emitir NFS-e",
)
async def emitir_nfse(
    nfse: NFSeEmissaoCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Emite NFS-e via API municipal.

    **Processo**:
    1. Gera XML do RPS (Recibo Provisório de Serviço)
    2. Envia para API municipal do município da empresa
    3. Obtém número da NFS-e gerada
    4. Salva no banco de dados

    **Padrão ABRASF**: A maioria dos municípios brasileiros utiliza
    o padrão ABRASF para emissão de NFS-e.

    **Campos obrigatórios**:
    - Tomador (dados do cliente/tomador do serviço)
    - Serviço (item da lista LC 116 + discriminação)
    - Valor dos serviços
    """
    user_id = usuario["id"]

    # Validar empresa pertence ao usuário
    emp = db.table("empresas").select("id").eq(
        "id", nfse.empresa_id
    ).eq("usuario_id", user_id).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    nfse_data = {
        "numero_rps": nfse.numero_rps,
        "serie_rps": nfse.serie_rps,
        "tomador": nfse.tomador.model_dump(),
        "servico": nfse.servico.model_dump(),
        "valor_servicos": str(nfse.valor_servicos),
        "valor_deducoes": str(nfse.valor_deducoes),
        "valor_pis": str(nfse.valor_pis),
        "valor_cofins": str(nfse.valor_cofins),
        "valor_inss": str(nfse.valor_inss),
        "valor_ir": str(nfse.valor_ir),
        "valor_csll": str(nfse.valor_csll),
        "iss_retido": nfse.iss_retido,
        "aliquota_iss": str(nfse.aliquota_iss),
        "valor_iss": str(nfse.valor_iss),
        "simples_nacional": nfse.simples_nacional,
    }

    resultado = await emissao_nfse_service.emitir_nfse(
        empresa_id=nfse.empresa_id,
        nfse_data=nfse_data,
        usuario_id=user_id,
    )

    return NFSeEmissaoResponse(**resultado)


# ============================================
# CANCELAMENTO
# ============================================

@router.post(
    "/cancelar",
    response_model=NFSeCancelamentoResponse,
    dependencies=[require_modules("emissor_notas")],
    summary="Cancelar NFS-e emitida",
)
async def cancelar_nfse(
    empresa_id: str = Body(..., embed=True),
    numero_nfse: str = Body(..., embed=True),
    codigo_cancelamento: str = Body(
        default="2", embed=True,
        description="1=Erro, 2=Serviço não prestado, 3=Duplicidade, 4=Processamento"
    ),
    motivo: str = Body(
        default="", embed=True, max_length=255
    ),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Cancela NFS-e emitida via API municipal.

    **Códigos de cancelamento**:
    - 1: Erro na emissão
    - 2: Serviço não prestado
    - 3: Duplicidade de nota
    - 4: Erro de processamento
    """
    emp = db.table("empresas").select("id").eq(
        "id", empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    resultado = await emissao_nfse_service.cancelar_nfse(
        empresa_id=empresa_id,
        numero_nfse=numero_nfse,
        codigo_cancelamento=codigo_cancelamento,
        motivo=motivo,
        usuario_id=usuario["id"],
    )

    return NFSeCancelamentoResponse(**resultado)


# ============================================
# MUNICÍPIOS SUPORTADOS
# ============================================

@router.get(
    "/municipios",
    response_model=List[MunicipioSuportado],
    summary="Listar municípios com suporte a emissão de NFS-e",
)
async def listar_municipios_emissao(
    uf: Optional[str] = Query(None, description="Filtrar por UF"),
):
    """
    Lista os 50 municípios com suporte à emissão de NFS-e.

    Inclui:
    - Top 10 com adapters específicos (API própria)
    - 40 municípios adicionais via padrão ABRASF / Sistema Nacional
    """
    from app.services.nfse.nfse_service import nfse_service

    # Top 10 com APIs próprias
    top10 = [
        MunicipioSuportado(
            codigo_ibge=m["codigo_ibge"],
            nome=m["nome"],
            uf=m["uf"],
            sistema=m["sistema"],
            status=m["status"],
        )
        for m in nfse_service.MUNICIPIOS_INFO
        if m["codigo_ibge"] != "default"
    ]

    # Adicionar 40 expandidos
    expandidos = [
        MunicipioSuportado(
            codigo_ibge=m["codigo"],
            nome=m["nome"],
            uf=m["uf"],
            sistema=m["sistema"],
            status="implementado",
        )
        for m in MUNICIPIOS_EXPANDIDOS
    ]

    todos = top10 + expandidos

    # Remover duplicados (por código IBGE)
    vistos = set()
    unicos = []
    for m in todos:
        if m.codigo_ibge not in vistos:
            vistos.add(m.codigo_ibge)
            unicos.append(m)

    # Filtrar por UF
    if uf:
        unicos = [m for m in unicos if m.uf.upper() == uf.upper()]

    return sorted(unicos, key=lambda x: x.nome)
