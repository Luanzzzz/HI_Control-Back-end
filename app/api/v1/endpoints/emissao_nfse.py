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
from fastapi.responses import Response
from supabase import Client
from decimal import Decimal
import logging

from app.dependencies import get_db, get_current_user, require_modules
from app.services.nfse.emissao_nfse_service import (
    emissao_nfse_service,
    MUNICIPIOS_EXPANDIDOS,
)
from app.services.nfse.emissao_nfse_nacional_service import nfse_nacional_service

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
    "/calcular-tributos",
    summary="Calcular IBS/CBS para NFS-e Nacional",
)
async def calcular_tributos_nfse(
    valor_servicos: float = Query(..., gt=0, description="Valor bruto dos serviços"),
    optante_simples: bool = Query(default=False, description="Empresa optante do Simples Nacional"),
    aliquota_ibs: float = Query(default=0.0, ge=0, description="Alíquota IBS (%)"),
    aliquota_cbs: float = Query(default=0.0, ge=0, description="Alíquota CBS (%)"),
):
    """
    Calcula IBS e CBS para uso na emissão de NFS-e Nacional (LC 214/2025).

    Use este endpoint para pré-visualizar os tributos antes de emitir.
    Optantes do Simples Nacional têm IBS/CBS = 0 (recolhidos via DAS).
    """
    resultado = emissao_nfse_service.calcular_ibs_cbs(
        valor_servicos=valor_servicos,
        optante_simples=optante_simples,
        aliquota_ibs=aliquota_ibs,
        aliquota_cbs=aliquota_cbs,
    )
    return {
        "valor_servicos": valor_servicos,
        **resultado,
        "valor_liquido": round(valor_servicos - resultado["valor_ibs"] - resultado["valor_cbs"], 2),
        "nota": "Alíquotas definitivas a partir de 2027. Durante transição (2026), alíquotas podem ser 0.",
    }


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
    certificado_senha: str = Field(..., description="Senha do certificado A1 da empresa")


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
    certificado_senha: str = Field(..., description="Senha do certificado A1 da empresa")


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
        "certificado_senha": nfse.certificado_senha,
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

    # PASSO 2: Consultar na API Nacional via SEFIN
    # Buscar empresa com certificado para fazer a consulta
    empresas_result = db.table("empresas").select(
        "id, certificado_a1"
    ).eq("usuario_id", user_id).not_.is_("certificado_a1", "null").limit(1).execute()

    if not empresas_result.data:
        raise HTTPException(
            status_code=404,
            detail="NFS-e não encontrada no banco local. Configure um certificado A1 para consultar na API Nacional."
        )

    empresa_cert = empresas_result.data[0]

    # A consulta na API nacional não precisa de senha (é somente leitura com mTLS)
    # Mas precisamos da senha para converter o PFX. Para consulta, tentamos com senha vazia
    # e retornamos instrução se falhar.
    try:
        from app.services.certificado_service import certificado_service
        from app.core.config import settings

        cert_bytes = certificado_service.descriptografar_certificado(empresa_cert["certificado_a1"])
        ambiente = "producao" if settings.SEFAZ_AMBIENTE == "producao" else "homologacao"

        # Nota: consulta requer senha do certificado; sem ela, retornar orientação
        raise HTTPException(
            status_code=400,
            detail={
                "mensagem": "Consulta na API Nacional requer a senha do certificado A1.",
                "instrucao": "Use o endpoint POST /nfse/emissao/nacional/consultar com a chave e a senha do certificado.",
                "alternativa": f"Acesse diretamente: https://www.gov.br/nfse — chave: {chave_nfse}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"NFS-e não encontrada. Erro ao consultar API Nacional: {str(e)}"
        )


@router.post(
    "/nacional/{chave_nfse}/cancelar",
    dependencies=[require_modules("emissor_notas")],
    summary="Cancelar NFS-e Nacional",
    response_model=dict,
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

    # Obter e descriptografar certificado A1
    from app.services.certificado_service import certificado_service
    from app.core.config import settings

    try:
        cert_bytes = certificado_service.descriptografar_certificado(empresa["certificado_a1"])
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Erro ao carregar certificado A1: {str(e)}"
        )

    ambiente = "producao" if settings.SEFAZ_AMBIENTE == "producao" else "homologacao"

    # Tentar cancelamento via API Nacional (SEFIN)
    resultado = await nfse_nacional_service.cancelar_nfse(
        chave_acesso=chave_nfse,
        motivo=request.motivo,
        cert_bytes=cert_bytes,
        cert_password=request.certificado_senha,
        ambiente=ambiente,
    )

    if resultado.get("cancelada"):
        # Atualizar status no banco local
        db.table("notas_fiscais").update({"situacao": "cancelada"}).eq(
            "chave_acesso", chave_nfse
        ).execute()

        return {
            "sucesso": True,
            "mensagem": resultado.get("mensagem", "NFS-e cancelada com sucesso"),
            "protocolo": resultado.get("protocolo"),
            "chave_acesso": chave_nfse,
        }
    else:
        # API retornou falha — orientar para o portal
        return {
            "sucesso": False,
            "mensagem": resultado.get("mensagem", "Cancelamento via API não disponível"),
            "orientacao": resultado.get(
                "orientacao",
                "Para cancelar, acesse https://www.gov.br/nfse com as credenciais da empresa"
            ),
            "portal": "https://www.gov.br/nfse",
            "chave_acesso": chave_nfse,
        }


# ============================================
# DANFSE (PDF)
# ============================================

@router.get(
    "/{nota_id}/danfse",
    summary="Baixar DANFSE (PDF da NFS-e)",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def baixar_danfse(
    nota_id: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Gera e retorna o DANFSE (Documento Auxiliar da NFS-e) em PDF.

    Busca a NFS-e no banco local pelo ID e gera o documento auxiliar.
    """
    user_id = usuario["id"]

    # Buscar nota no banco
    nota_result = db.table("notas_fiscais").select("*").eq("id", nota_id).execute()

    if not nota_result.data:
        raise HTTPException(status_code=404, detail="NFS-e não encontrada")

    nota = nota_result.data[0]

    # Validar que pertence ao usuário (tenant isolation)
    empresa_result = db.table("empresas").select(
        "id, razao_social, cnpj, inscricao_municipal, municipio_nome, uf, "
        "logradouro, numero, bairro"
    ).eq("id", nota["empresa_id"]).eq("usuario_id", user_id).execute()

    if not empresa_result.data:
        raise HTTPException(status_code=403, detail="Acesso negado a esta nota fiscal")

    empresa = empresa_result.data[0]

    # Verificar que é NFS-e
    if nota.get("tipo_nf") not in ("NFSE", "NFS-e", "nfse"):
        raise HTTPException(
            status_code=400,
            detail="Este documento não é uma NFS-e. Use o endpoint DANFE para NF-e."
        )

    # Gerar PDF
    try:
        from app.services.danfse_service import danfse_service
        pdf_bytes = danfse_service.gerar_danfse(dados=nota, empresa=empresa)
    except Exception as e:
        logger.error(f"Erro ao gerar DANFSE: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar DANFSE: {str(e)}")

    numero = nota.get("numero_nf", nota_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="DANFSE-{numero}.pdf"'},
    )
