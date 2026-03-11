"""
Endpoints de suporte à interface de emissão de NF-e/NFC-e.

Funcionalidades:
- Numeração fiscal (auto-incremento)
- Tabela CFOP (consulta e busca)
- Tabela NCM (consulta e busca)
- Produtos cadastrados (CRUD)
- Validação de dados fiscais
- Status de contingência
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from supabase import Client
from decimal import Decimal
import logging
import re

from app.dependencies import get_db, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emissao/suporte", tags=["Emissão - Suporte"])


# ============================================
# SCHEMAS
# ============================================

class NumeracaoResponse(BaseModel):
    proximo_numero: int
    ultimo_utilizado: int
    modelo: str
    serie: str


class CFOPItem(BaseModel):
    codigo: str
    descricao: str
    tipo: Optional[str] = None


class NCMItem(BaseModel):
    codigo: str
    descricao: str


class ProdutoCreate(BaseModel):
    empresa_id: str
    codigo: str = Field(..., max_length=60)
    descricao: str = Field(..., max_length=120)
    ncm: str = Field(..., pattern=r"^\d{8}$")
    cfop: str = Field(..., pattern=r"^\d{4}$")
    unidade: str = Field(default="UN", max_length=6)
    valor_unitario: Decimal = Field(..., ge=0)
    ean: Optional[str] = Field(None, max_length=14)
    cst_icms: str = Field(default="00")
    aliquota_icms: Decimal = Field(default=Decimal("0"))
    cst_pis: str = Field(default="99")
    cst_cofins: str = Field(default="99")
    origem: str = Field(
        default="0", description="0=Nacional, 1=Estrangeira importação direta, etc."
    )


class ProdutoResponse(BaseModel):
    id: str
    empresa_id: str
    codigo: str
    descricao: str
    ncm: str
    cfop: str
    unidade: str
    valor_unitario: float
    ean: Optional[str] = None
    cst_icms: str
    aliquota_icms: float
    cst_pis: str
    cst_cofins: str
    origem: str
    ativo: bool = True


class ValidacaoRequest(BaseModel):
    """Dados para validação pré-emissão."""
    empresa_id: str
    modelo: str = Field(default="55", pattern=r"^(55|65)$")
    destinatario_cnpj: Optional[str] = None
    destinatario_cpf: Optional[str] = None
    itens: list[dict] = Field(default_factory=list)


class ValidacaoResponse(BaseModel):
    valido: bool
    erros: list[str] = []
    avisos: list[str] = []


# ============================================
# NUMERAÇÃO FISCAL
# ============================================

@router.get(
    "/numeracao/{empresa_id}",
    response_model=NumeracaoResponse,
    summary="Obter próximo número de NF-e/NFC-e",
)
async def obter_numeracao(
    empresa_id: str,
    modelo: str = Query(default="55", regex=r"^(55|65)$"),
    serie: str = Query(default="1"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Retorna o próximo número disponível para emissão.

    **Parâmetros**:
    - `modelo`: 55 (NF-e) ou 65 (NFC-e)
    - `serie`: Série da nota (padrão: 1)

    A numeração é gerenciada automaticamente pelo sistema.
    """
    # Validar que empresa pertence ao usuário
    emp = db.table("empresas").select("id").eq(
        "id", empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    result = db.table("numeracao_fiscal").select("*").eq(
        "empresa_id", empresa_id
    ).eq("modelo", modelo).eq("serie", serie).execute()

    if result.data:
        ultimo = result.data[0]["ultimo_numero"]
        return NumeracaoResponse(
            proximo_numero=ultimo + 1,
            ultimo_utilizado=ultimo,
            modelo=modelo,
            serie=serie,
        )

    # Criar registro inicial
    db.table("numeracao_fiscal").insert({
        "empresa_id": empresa_id,
        "modelo": modelo,
        "serie": serie,
        "ultimo_numero": 0,
    }).execute()

    return NumeracaoResponse(
        proximo_numero=1,
        ultimo_utilizado=0,
        modelo=modelo,
        serie=serie,
    )


# ============================================
# CFOP
# ============================================

@router.get(
    "/cfop",
    response_model=List[CFOPItem],
    summary="Listar códigos CFOP",
)
async def listar_cfop(
    busca: Optional[str] = Query(None, description="Busca por código ou descrição"),
    tipo: Optional[str] = Query(
        None, description="Filtrar por tipo: entrada, saida, estadual, interestadual"
    ),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: Client = Depends(get_db),
):
    """
    Lista códigos CFOP disponíveis.

    **Filtros**:
    - `busca`: Texto para busca em código ou descrição
    - `tipo`: Filtro por tipo de operação

    **Exemplos de CFOP comuns**:
    - 5102: Venda de mercadoria adquirida (dentro do estado)
    - 6102: Venda de mercadoria adquirida (fora do estado)
    - 5405: Venda de mercadoria ST (substituição tributária)
    """
    query = db.table("cfop_tabela").select("codigo, descricao, tipo")

    if busca:
        query = query.or_(f"codigo.ilike.%{busca}%,descricao.ilike.%{busca}%")

    if tipo:
        query = query.eq("tipo", tipo)

    result = query.range(offset, offset + limit - 1).execute()

    return [
        CFOPItem(
            codigo=r["codigo"],
            descricao=r["descricao"],
            tipo=r.get("tipo"),
        )
        for r in (result.data or [])
    ]


@router.get(
    "/cfop/{codigo}",
    response_model=CFOPItem,
    summary="Consultar CFOP por código",
)
async def consultar_cfop(
    codigo: str,
    db: Client = Depends(get_db),
):
    """Retorna detalhes de um CFOP específico."""
    result = db.table("cfop_tabela").select("*").eq("codigo", codigo).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"CFOP {codigo} não encontrado")

    r = result.data[0]
    return CFOPItem(codigo=r["codigo"], descricao=r["descricao"], tipo=r.get("tipo"))


# ============================================
# NCM
# ============================================

@router.get(
    "/ncm",
    response_model=List[NCMItem],
    summary="Listar códigos NCM",
)
async def listar_ncm(
    busca: Optional[str] = Query(
        None, description="Busca por código ou descrição"
    ),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: Client = Depends(get_db),
):
    """
    Lista códigos NCM (Nomenclatura Comum do Mercosul).

    Use `busca` para filtrar por código ou descrição.
    """
    query = db.table("ncm_tabela").select("codigo, descricao")

    if busca:
        query = query.or_(f"codigo.ilike.%{busca}%,descricao.ilike.%{busca}%")

    result = query.range(offset, offset + limit - 1).execute()

    return [
        NCMItem(codigo=r["codigo"], descricao=r["descricao"])
        for r in (result.data or [])
    ]


@router.get(
    "/ncm/{codigo}",
    response_model=NCMItem,
    summary="Consultar NCM por código",
)
async def consultar_ncm(
    codigo: str,
    db: Client = Depends(get_db),
):
    """Retorna detalhes de um NCM específico."""
    result = db.table("ncm_tabela").select("*").eq("codigo", codigo).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail=f"NCM {codigo} não encontrado")

    r = result.data[0]
    return NCMItem(codigo=r["codigo"], descricao=r["descricao"])


# ============================================
# PRODUTOS CADASTRADOS
# ============================================

@router.get(
    "/produtos/{empresa_id}",
    response_model=List[ProdutoResponse],
    summary="Listar produtos cadastrados",
)
async def listar_produtos(
    empresa_id: str,
    busca: Optional[str] = Query(None),
    ativo: bool = Query(default=True),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Lista produtos cadastrados da empresa para uso na emissão."""
    # Validar empresa
    emp = db.table("empresas").select("id").eq(
        "id", empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    query = db.table("produtos_cadastrados").select("*").eq(
        "empresa_id", empresa_id
    ).eq("ativo", ativo)

    if busca:
        query = query.or_(
            f"codigo.ilike.%{busca}%,descricao.ilike.%{busca}%,ean.ilike.%{busca}%"
        )

    result = query.order("descricao").range(offset, offset + limit - 1).execute()

    return [
        ProdutoResponse(
            id=r["id"],
            empresa_id=r["empresa_id"],
            codigo=r["codigo"],
            descricao=r["descricao"],
            ncm=r["ncm"],
            cfop=r["cfop"],
            unidade=r.get("unidade", "UN"),
            valor_unitario=float(r.get("valor_unitario", 0)),
            ean=r.get("ean"),
            cst_icms=r.get("cst_icms", "00"),
            aliquota_icms=float(r.get("aliquota_icms", 0)),
            cst_pis=r.get("cst_pis", "99"),
            cst_cofins=r.get("cst_cofins", "99"),
            origem=r.get("origem", "0"),
            ativo=r.get("ativo", True),
        )
        for r in (result.data or [])
    ]


@router.post(
    "/produtos",
    response_model=ProdutoResponse,
    status_code=201,
    summary="Cadastrar produto",
)
async def cadastrar_produto(
    produto: ProdutoCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Cadastra um produto para uso na emissão de NF-e/NFC-e.

    Produtos cadastrados facilitam o preenchimento da nota,
    evitando retrabalho e erros.
    """
    # Validar empresa
    emp = db.table("empresas").select("id").eq(
        "id", produto.empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    # Verificar duplicidade
    dup = db.table("produtos_cadastrados").select("id").eq(
        "empresa_id", produto.empresa_id
    ).eq("codigo", produto.codigo).execute()

    if dup.data:
        raise HTTPException(
            status_code=409,
            detail=f"Produto com código '{produto.codigo}' já cadastrado.",
        )

    data = {
        "empresa_id": produto.empresa_id,
        "codigo": produto.codigo,
        "descricao": produto.descricao,
        "ncm": produto.ncm,
        "cfop": produto.cfop,
        "unidade": produto.unidade,
        "valor_unitario": float(produto.valor_unitario),
        "ean": produto.ean,
        "cst_icms": produto.cst_icms,
        "aliquota_icms": float(produto.aliquota_icms),
        "cst_pis": produto.cst_pis,
        "cst_cofins": produto.cst_cofins,
        "origem": produto.origem,
        "ativo": True,
    }

    result = db.table("produtos_cadastrados").insert(data).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao cadastrar produto")

    r = result.data[0]
    return ProdutoResponse(
        id=r["id"],
        empresa_id=r["empresa_id"],
        codigo=r["codigo"],
        descricao=r["descricao"],
        ncm=r["ncm"],
        cfop=r["cfop"],
        unidade=r.get("unidade", "UN"),
        valor_unitario=float(r.get("valor_unitario", 0)),
        ean=r.get("ean"),
        cst_icms=r.get("cst_icms", "00"),
        aliquota_icms=float(r.get("aliquota_icms", 0)),
        cst_pis=r.get("cst_pis", "99"),
        cst_cofins=r.get("cst_cofins", "99"),
        origem=r.get("origem", "0"),
        ativo=r.get("ativo", True),
    )


@router.put(
    "/produtos/{produto_id}",
    response_model=ProdutoResponse,
    summary="Atualizar produto",
)
async def atualizar_produto(
    produto_id: str,
    produto: ProdutoCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Atualiza dados de um produto cadastrado."""
    # Validar empresa
    emp = db.table("empresas").select("id").eq(
        "id", produto.empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    data = {
        "codigo": produto.codigo,
        "descricao": produto.descricao,
        "ncm": produto.ncm,
        "cfop": produto.cfop,
        "unidade": produto.unidade,
        "valor_unitario": float(produto.valor_unitario),
        "ean": produto.ean,
        "cst_icms": produto.cst_icms,
        "aliquota_icms": float(produto.aliquota_icms),
        "cst_pis": produto.cst_pis,
        "cst_cofins": produto.cst_cofins,
        "origem": produto.origem,
    }

    result = db.table("produtos_cadastrados").update(data).eq(
        "id", produto_id
    ).eq("empresa_id", produto.empresa_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    r = result.data[0]
    return ProdutoResponse(
        id=r["id"],
        empresa_id=r["empresa_id"],
        codigo=r["codigo"],
        descricao=r["descricao"],
        ncm=r["ncm"],
        cfop=r["cfop"],
        unidade=r.get("unidade", "UN"),
        valor_unitario=float(r.get("valor_unitario", 0)),
        ean=r.get("ean"),
        cst_icms=r.get("cst_icms", "00"),
        aliquota_icms=float(r.get("aliquota_icms", 0)),
        cst_pis=r.get("cst_pis", "99"),
        cst_cofins=r.get("cst_cofins", "99"),
        origem=r.get("origem", "0"),
        ativo=r.get("ativo", True),
    )


@router.delete(
    "/produtos/{produto_id}",
    summary="Desativar produto",
)
async def desativar_produto(
    produto_id: str,
    empresa_id: str = Query(...),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Desativa (soft delete) um produto cadastrado."""
    emp = db.table("empresas").select("id").eq(
        "id", empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    db.table("produtos_cadastrados").update({"ativo": False}).eq(
        "id", produto_id
    ).eq("empresa_id", empresa_id).execute()

    return {"mensagem": "Produto desativado com sucesso"}


# ============================================
# VALIDAÇÃO PRÉ-EMISSÃO
# ============================================

@router.post(
    "/validar",
    response_model=ValidacaoResponse,
    summary="Validar dados antes da emissão",
)
async def validar_pre_emissao(
    dados: ValidacaoRequest,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Valida os dados de uma NF-e/NFC-e antes de enviar para SEFAZ.

    Verifica:
    - Empresa possui certificado digital válido
    - CSC configurado (para NFC-e)
    - CNPJ/CPF do destinatário válido
    - Itens com NCM e CFOP válidos
    - Valores consistentes
    """
    erros = []
    avisos = []

    # 1. Validar empresa
    emp = db.table("empresas").select("*").eq(
        "id", dados.empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        erros.append("Empresa não encontrada ou não pertence ao usuário")
        return ValidacaoResponse(valido=False, erros=erros, avisos=avisos)

    empresa = emp.data[0]

    # 2. Certificado
    if not empresa.get("certificado_a1"):
        erros.append("Certificado digital A1 não cadastrado")
    else:
        from app.services.certificado_service import certificado_service
        cert_status = certificado_service.verificar_expiracao(
            empresa.get("certificado_validade")
        )
        if cert_status["status"] == "expirado":
            erros.append(f"Certificado digital expirado: {cert_status['alerta']}")
        elif cert_status["status"] == "expirando_em_breve":
            avisos.append(f"Certificado expirando: {cert_status['alerta']}")

    # 3. CSC (NFC-e)
    if dados.modelo == "65":
        if not empresa.get("csc_id") or not empresa.get("csc_token"):
            erros.append(
                "CSC não configurado. Obrigatório para emissão de NFC-e."
            )

    # 4. Destinatário
    if dados.destinatario_cnpj:
        if not _validar_cnpj(dados.destinatario_cnpj):
            erros.append(f"CNPJ do destinatário inválido: {dados.destinatario_cnpj}")

    if dados.destinatario_cpf:
        if not _validar_cpf(dados.destinatario_cpf):
            erros.append(f"CPF do destinatário inválido: {dados.destinatario_cpf}")

    # 5. Itens
    if not dados.itens:
        if dados.modelo == "55":
            erros.append("NF-e deve conter pelo menos 1 item")
        # NFC-e também
        erros.append("A nota deve conter pelo menos 1 item")
    else:
        for i, item in enumerate(dados.itens, 1):
            ncm = item.get("ncm", "")
            if ncm and not re.match(r"^\d{8}$", ncm):
                erros.append(f"Item {i}: NCM inválido ({ncm}). Deve ter 8 dígitos.")

            cfop = item.get("cfop", "")
            if cfop and not re.match(r"^\d{4}$", cfop):
                erros.append(f"Item {i}: CFOP inválido ({cfop}). Deve ter 4 dígitos.")

            valor = item.get("valor_total", 0)
            if float(valor) <= 0:
                erros.append(f"Item {i}: Valor total deve ser maior que zero.")

    # 6. Contingência
    from app.services.contingencia_service import contingencia_service
    if contingencia_service.em_contingencia:
        avisos.append(
            f"Sistema em modo de contingência: "
            f"{contingencia_service.obter_status()['modo_nome']}"
        )

    return ValidacaoResponse(
        valido=len(erros) == 0,
        erros=erros,
        avisos=avisos,
    )


# ============================================
# STATUS CONTINGÊNCIA
# ============================================

@router.get(
    "/contingencia/status",
    summary="Status do modo de contingência",
)
async def status_contingencia(
    usuario: dict = Depends(get_current_user),
):
    """Retorna status atual do modo de contingência."""
    from app.services.contingencia_service import contingencia_service
    return contingencia_service.obter_status()


@router.get(
    "/contingencia",
    summary="Verificar contingência (alias)",
)
async def verificar_contingencia(
    usuario: dict = Depends(get_current_user),
):
    """
    Alias para /contingencia/status.
    Verifica se SEFAZ está em contingência.
    """
    from app.services.contingencia_service import contingencia_service
    status = contingencia_service.obter_status()
    return {
        "success": True,
        "data": {
            "contingencia_ativa": status["em_contingencia"],
            "modo": status["modo"],
            "modo_nome": status["modo_nome"],
            "mensagem": status["motivo"] or "SEFAZ operando normalmente",
        }
    }


# ============================================
# VALIDAÇÃO AUXILIAR
# ============================================

def _validar_cnpj(cnpj: str) -> bool:
    """Valida CNPJ usando dígitos verificadores."""
    cnpj = re.sub(r"\D", "", cnpj)
    if len(cnpj) != 14:
        return False
    if cnpj == cnpj[0] * 14:
        return False

    def calc_digit(cnpj_parcial, pesos):
        soma = sum(int(c) * p for c, p in zip(cnpj_parcial, pesos))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    d1 = calc_digit(cnpj[:12], pesos1)
    d2 = calc_digit(cnpj[:13], pesos2)

    return cnpj[-2:] == f"{d1}{d2}"


def _validar_cpf(cpf: str) -> bool:
    """Valida CPF usando dígitos verificadores."""
    cpf = re.sub(r"\D", "", cpf)
    if len(cpf) != 11:
        return False
    if cpf == cpf[0] * 11:
        return False

    def calc_digit(cpf_parcial, start_weight):
        soma = sum(int(c) * p for c, p in zip(
            cpf_parcial, range(start_weight, 1, -1)
        ))
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    d1 = calc_digit(cpf[:9], 10)
    d2 = calc_digit(cpf[:10], 11)

    return cpf[-2:] == f"{d1}{d2}"
