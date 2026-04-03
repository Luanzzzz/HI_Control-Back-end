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


# ============================================
# NFS-e NACIONAL (SEFIN)
# ============================================

class NFSeNacionalTomadorCreate(BaseModel):
    """Dados do tomador para emissão nacional."""
    cnpj_cpf: str = Field(..., description="CNPJ ou CPF do tomador")
    razao_social: str = Field(..., max_length=200)
    email: Optional[str] = None
    endereco: Optional[dict] = Field(
        None,
        description="Endereço completo: logradouro, numero, bairro, codigo_municipio, uf, cep"
    )


class NFSeNacionalServicoCreate(BaseModel):
    """Dados do serviço para emissão nacional."""
    codigo_servico: str = Field(..., description="Código do serviço LC 116 (ex: 01.01)")
    descricao: str = Field(..., max_length=2000)
    valor: Decimal = Field(..., gt=0)
    municipio_prestacao: str = Field(..., min_length=7, max_length=7, description="Código IBGE 7 dígitos")


class NFSeNacionalEmissaoCreate(BaseModel):
    """Request para emissão de NFS-e Nacional via SEFIN."""
    empresa_id: str
    tomador: NFSeNacionalTomadorCreate
    servico: NFSeNacionalServicoCreate
    competencia: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Mês de referência YYYY-MM")
    regime_especial: Optional[str] = None
    optante_simples: bool = Field(default=False)


class NFSeNacionalEmissaoResponse(BaseModel):
    """Response da emissão nacional."""
    chave_nfse: Optional[str] = None
    numero_nfse: Optional[str] = None
    status: str = Field(..., description="autorizada | em_processamento | rejeitada")
    protocolo: Optional[str] = None
    data_emissao: Optional[str] = None
    erro: Optional[str] = None
    codigo: Optional[str] = None
    detalhes: Optional[List[str]] = None


class NFSeNacionalCancelamentoRequest(BaseModel):
    """Request de cancelamento nacional."""
    motivo: str = Field(..., min_length=15, description="Justificativa do cancelamento")


@router.post(
    "/emitir-nacional",
    response_model=NFSeNacionalEmissaoResponse,
    dependencies=[require_modules("emissor_notas")],
    status_code=201,
    summary="Emitir NFS-e Nacional via SEFIN",
)
async def emitir_nfse_nacional(
    nfse: NFSeNacionalEmissaoCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Emite NFS-e no padrão Nacional (SEFIN).

    **Validações obrigatórias**:
    - Empresa pertence ao usuário autenticado (tenant isolation)
    - Empresa tem certificado A1 configurado
    - Empresa tem municipio_codigo configurado
    - Usuário tem plano com módulo de emissão

    **Processo**:
    1. Monta DPS (Documento Padrão de Serviço) com IBS/CBS
    2. Envia para SEFIN Nacional via mTLS
    3. Retorna chave de acesso e número da NFS-e
    4. Salva no banco de dados local
    """
    user_id = usuario["id"]

    # VALIDAÇÃO 1: Empresa pertence ao usuário (tenant isolation)
    empresa_result = db.table("empresas").select(
        "id, certificado_a1, municipio_codigo, municipio_nome"
    ).eq("id", nfse.empresa_id).eq("usuario_id", user_id).execute()

    if not empresa_result.data:
        raise HTTPException(
            status_code=404,
            detail="Empresa não encontrada ou não pertence ao usuário"
        )

    empresa = empresa_result.data[0]

    # VALIDAÇÃO 2: Certificado A1 configurado
    if not empresa.get("certificado_a1"):
        raise HTTPException(
            status_code=400,
            detail="Empresa não possui certificado A1 configurado. "
                   "Configure o certificado digital antes de emitir NFS-e."
        )

    # VALIDAÇÃO 3: municipio_codigo configurado
    if not empresa.get("municipio_codigo"):
        raise HTTPException(
            status_code=400,
            detail="Empresa não possui código do município (IBGE) configurado. "
                   "Atualize os dados da empresa com o código IBGE do município."
        )

    # VALIDAÇÃO 4: Plano com módulo de emissão (já validado por require_modules)

    # Preparar dados para emissão
    from app.services.nfse.emissao_nfse_service import emissao_nfse_service

    # Converter para formato esperado pelo service
    tomador_dict = nfse.tomador.model_dump()
    servico_dict = nfse.servico.model_dump()

    # Determinar se é CNPJ ou CPF
    cnpj_cpf_limpo = ''.join(filter(str.isdigit, tomador_dict["cnpj_cpf"]))
    if len(cnpj_cpf_limpo) == 14:
        tomador_dict["cnpj"] = cnpj_cpf_limpo
        tomador_dict.pop("cnpj_cpf", None)
    elif len(cnpj_cpf_limpo) == 11:
        tomador_dict["cpf"] = cnpj_cpf_limpo
        tomador_dict.pop("cnpj_cpf", None)
    else:
        raise HTTPException(
            status_code=400,
            detail="CNPJ/CPF do tomador inválido. Deve ter 11 (CPF) ou 14 (CNPJ) dígitos."
        )

    # Renomear campos para o padrão do service
    servico_dict["discriminacao"] = servico_dict.pop("descricao")
    servico_dict["valor_servicos"] = servico_dict.pop("valor")
    servico_dict["codigo_tributacao_nacional"] = servico_dict.pop("codigo_servico")
    servico_dict["codigo_municipio"] = servico_dict.pop("municipio_prestacao")

    nfse_data = {
        "tomador": tomador_dict,
        "servico": servico_dict,
        "competencia": nfse.competencia,
        "regime_especial": nfse.regime_especial,
        "optante_simples": nfse.optante_simples,
    }

    # Chamar service de emissão com flag usar_nacional=True
    resultado = await emissao_nfse_service.emitir_nfse(
        empresa_id=nfse.empresa_id,
        nfse_data=nfse_data,
        usuario_id=user_id,
        usar_nacional=True,  # Forçar uso da API Nacional
    )

    # Mapear resposta
    if resultado.get("sucesso"):
        return NFSeNacionalEmissaoResponse(
            chave_nfse=resultado.get("chave_acesso"),
            numero_nfse=resultado.get("numero_nfse"),
            status="autorizada",
            protocolo=resultado.get("protocolo"),
            data_emissao=resultado.get("data_emissao"),
        )
    else:
        return NFSeNacionalEmissaoResponse(
            status="rejeitada",
            erro=resultado.get("mensagem", resultado.get("erro")),
            codigo=resultado.get("codigo_http"),
            detalhes=resultado.get("detalhes", []) if isinstance(resultado.get("detalhes"), list) else [str(resultado.get("detalhes", ""))],
        )


@router.get(
    "/nacional/{chave_nfse}",
    summary="Consultar NFS-e Nacional por chave",
)
async def consultar_nfse_nacional(
    chave_nfse: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Consulta NFS-e Nacional por chave de acesso.

    **Processo**:
    1. Busca primeiro no banco de dados local
    2. Se não encontrar: consulta API Nacional (requer certificado)
    3. Retorna dados completos da nota

    **Chave de acesso**: 44 dígitos numéricos
    """
    from app.services.nfse.emissao_nfse_nacional_service import nfse_nacional_service

    # Validar formato da chave
    if len(chave_nfse) != 44 or not chave_nfse.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Chave de acesso inválida. Deve conter 44 dígitos numéricos."
        )

    user_id = usuario["id"]

    # PASSO 1: Buscar no banco local
    nota_result = db.table("notas_fiscais").select("*").eq(
        "chave_acesso", chave_nfse
    ).execute()

    if nota_result.data:
        nota = nota_result.data[0]

        # Verificar se a nota pertence a uma empresa do usuário (tenant isolation)
        empresa_result = db.table("empresas").select("id").eq(
            "id", nota["empresa_id"]
        ).eq("usuario_id", user_id).execute()

        if not empresa_result.data:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado a esta nota fiscal"
            )

        return {
            "origem": "banco_local",
            "nota": nota
        }

    # PASSO 2: Consultar na API Nacional
    # Para consultar na API, precisa de certificado de alguma empresa do usuário
    empresas_result = db.table("empresas").select(
        "id, certificado_a1"
    ).eq("usuario_id", user_id).limit(1).execute()

    if not empresas_result.data or not empresas_result.data[0].get("certificado_a1"):
        raise HTTPException(
            status_code=404,
            detail="NFS-e não encontrada no banco local e não há certificado configurado para consulta na API Nacional"
        )

    # TODO: Implementar consulta na API Nacional usando certificado
    # Por ora, retornar não encontrado
    raise HTTPException(
        status_code=404,
        detail="NFS-e não encontrada no banco local. Consulta na API Nacional em desenvolvimento."
    )


@router.post(
    "/nacional/{chave_nfse}/cancelar",
    dependencies=[require_modules("emissor_notas")],
    summary="Cancelar NFS-e Nacional",
)
async def cancelar_nfse_nacional(
    chave_nfse: str,
    request: NFSeNacionalCancelamentoRequest,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Cancela NFS-e Nacional via SEFIN.

    **Validações**:
    - Chave de acesso válida (44 dígitos)
    - Motivo com mínimo 15 caracteres
    - Nota pertence a empresa do usuário
    - Empresa tem certificado A1 configurado

    **Processo**:
    1. Valida permissões e dados
    2. Envia evento de cancelamento para SEFIN
    3. Atualiza status no banco local
    """
    from app.services.nfse.emissao_nfse_nacional_service import nfse_nacional_service

    # Validar formato da chave
    if len(chave_nfse) != 44 or not chave_nfse.isdigit():
        raise HTTPException(
            status_code=400,
            detail="Chave de acesso inválida. Deve conter 44 dígitos numéricos."
        )

    user_id = usuario["id"]

    # Buscar nota no banco local
    nota_result = db.table("notas_fiscais").select(
        "id, empresa_id, situacao"
    ).eq("chave_acesso", chave_nfse).execute()

    if not nota_result.data:
        raise HTTPException(
            status_code=404,
            detail="NFS-e não encontrada"
        )

    nota = nota_result.data[0]

    # Verificar tenant isolation
    empresa_result = db.table("empresas").select(
        "id, certificado_a1"
    ).eq("id", nota["empresa_id"]).eq("usuario_id", user_id).execute()

    if not empresa_result.data:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado a esta nota fiscal"
        )

    empresa = empresa_result.data[0]

    # Validar certificado
    if not empresa.get("certificado_a1"):
        raise HTTPException(
            status_code=400,
            detail="Empresa não possui certificado A1 configurado"
        )

    # Validar situação da nota
    if nota["situacao"] == "cancelada":
        raise HTTPException(
            status_code=400,
            detail="NFS-e já está cancelada"
        )

    # NOTA: Endpoint de cancelamento não confirmado na API SEFIN Nacional.
    # O cancelamento via API requer confirmação da documentação oficial.
    # Para cancelar, use o portal: https://www.gov.br/nfse
    raise HTTPException(
        status_code=501,
        detail={
            "message": "Cancelamento de NFS-e Nacional não está disponível via API nesta versão.",
            "instrucoes": [
                "Para cancelar uma NFS-e Nacional, acesse https://www.gov.br/nfse",
                "Faça login com as credenciais da empresa emitente",
                "Selecione a nota pela chave de acesso ou número",
                "Solicite o cancelamento com motivo válido"
            ],
            "chave_acesso": chave_nfse,
            "portal": "https://www.gov.br/nfse",
            "documentacao": "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica",
            "funcionalidade_prevista": "v2.0"
        }
    )
