"""
Endpoints para emissão de CT-e (Conhecimento de Transporte Eletrônico - Modelo 57).

Funcionalidades:
- Autorização de CT-e
- Consulta de CT-e por chave de acesso
- Cancelamento de CT-e
- Geração de DACTE (PDF)
- Listagem de CT-e emitidos
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from fastapi.responses import StreamingResponse
from supabase import Client
from datetime import datetime
from decimal import Decimal
import logging

from app.dependencies import get_db, get_current_user, require_modules
from app.services.cte_service import cte_service
from app.services.certificado_service import certificado_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cte", tags=["CT-e - Transporte"])


# ============================================
# SCHEMAS
# ============================================

class CTeEnderecoCreate(BaseModel):
    cnpj: Optional[str] = None
    cpf: Optional[str] = None
    nome: str = Field(..., max_length=100)
    ie: Optional[str] = None
    fantasia: Optional[str] = None
    logradouro: str = Field(default="", max_length=60)
    numero: str = Field(default="SN", max_length=10)
    bairro: str = Field(default="", max_length=60)
    municipio: str = Field(default="")
    codigo_municipio: str = Field(default="0000000")
    uf: str = Field(default="", max_length=2)
    cep: str = Field(default="", max_length=8)


class CTeCargaCreate(BaseModel):
    valor: Decimal = Field(default=Decimal("0"), ge=0)
    produto_predominante: str = Field(
        default="MERCADORIAS EM GERAL", max_length=120
    )
    quantidade: Decimal = Field(default=Decimal("0"), ge=0)
    unidade_medida: str = Field(default="KG", max_length=5)


class CTeNFeVinculada(BaseModel):
    chave_acesso: str = Field(..., pattern=r"^\d{44}$")


class CTeCreate(BaseModel):
    """Dados para emissão de CT-e."""
    empresa_id: str

    # SEGURANÇA: Senha do certificado A1 não é armazenada no banco.
    # Deve ser fornecida a cada requisição de emissão.
    certificado_senha: str = Field(
        ...,
        min_length=1,
        description="Senha do certificado A1 para assinatura digital do CT-e"
    )

    serie: str = Field(default="1", max_length=3)
    numero_ct: Optional[str] = Field(
        None, description="Número do CT-e (auto se vazio)"
    )
    tipo_cte: str = Field(
        default="0", description="0=Normal, 1=Complementar, 2=Anulação, 3=Substituto"
    )
    modal: str = Field(
        default="01", description="01=Rodoviário, 02=Aéreo, 03=Aquaviário, "
                                  "04=Ferroviário, 05=Dutoviário"
    )
    tipo_servico: str = Field(
        default="0", description="0=Normal, 1=Subcontratação, 2=Redespacho, "
                                 "3=Redespacho Intermediário"
    )
    cfop: str = Field(default="5353", pattern=r"^\d{4}$")
    natureza_operacao: str = Field(
        default="PRESTACAO DE SERVICO DE TRANSPORTE", max_length=60
    )

    remetente: CTeEnderecoCreate
    destinatario: CTeEnderecoCreate
    expedidor: Optional[CTeEnderecoCreate] = None
    recebedor: Optional[CTeEnderecoCreate] = None

    valor_total_servico: Decimal = Field(..., gt=0)
    valor_receber: Optional[Decimal] = None
    aliquota_icms: Decimal = Field(default=Decimal("12.00"))
    valor_icms: Decimal = Field(default=Decimal("0"))

    carga: CTeCargaCreate = Field(default_factory=CTeCargaCreate)
    nfe_vinculadas: List[CTeNFeVinculada] = Field(default_factory=list)

    # Rodoviário
    rntrc: Optional[str] = Field(None, description="RNTRC da empresa")

    info_complementar: Optional[str] = Field(None, max_length=2000)
    ambiente: str = Field(default="2", description="1=Produção, 2=Homologação")


class CTeResponse(BaseModel):
    id: Optional[str] = None
    autorizado: bool
    chave_acesso: Optional[str] = None
    protocolo: Optional[str] = None
    numero_ct: Optional[str] = None
    serie: Optional[str] = None
    status_codigo: Optional[str] = None
    status_descricao: Optional[str] = None
    erro: Optional[str] = None


class CTeListItem(BaseModel):
    id: str
    numero_ct: str
    serie: str
    chave_acesso: Optional[str] = None
    situacao: str
    rem_nome: Optional[str] = None
    dest_nome: Optional[str] = None
    valor_total_servico: float
    data_emissao: Optional[str] = None
    modal: Optional[str] = None


# ============================================
# AUTORIZAÇÃO CT-e
# ============================================

@router.post(
    "/autorizar",
    response_model=CTeResponse,
    dependencies=[require_modules("emissor_notas")],
    status_code=201,
    summary="Autorizar CT-e (modelo 57)",
)
async def autorizar_cte(
    cte: CTeCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Autoriza um CT-e junto à SEFAZ.

    **Modais suportados**:
    - 01: Rodoviário
    - 02: Aéreo
    - 03: Aquaviário
    - 04: Ferroviário
    - 05: Dutoviário

    **Campos obrigatórios**:
    - Remetente e destinatário
    - Valor total do serviço
    - Dados da carga
    - CFOP
    """
    user_id = usuario["id"]

    try:
        # 1. Validar empresa
        result = db.table("empresas").select("*").eq(
            "id", cte.empresa_id
        ).eq("usuario_id", user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        empresa = result.data[0]

        # 2. Validar certificado
        if not empresa.get("certificado_a1"):
            raise HTTPException(
                status_code=400,
                detail="Certificado digital não cadastrado.",
            )

        cert_bytes = certificado_service.descriptografar_certificado(
            empresa["certificado_a1"]
        )

        # SEGURANÇA: Senha vem do request (não do banco) para evitar exposição
        senha_cert = cte.certificado_senha

        # 3. Auto-incremento
        numero_ct = cte.numero_ct
        if not numero_ct:
            num_result = db.table("numeracao_fiscal").select("ultimo_numero").eq(
                "empresa_id", cte.empresa_id
            ).eq("modelo", "57").eq("serie", cte.serie).execute()

            if num_result.data:
                numero_ct = str(num_result.data[0]["ultimo_numero"] + 1)
            else:
                db.table("numeracao_fiscal").insert({
                    "empresa_id": cte.empresa_id,
                    "modelo": "57",
                    "serie": cte.serie,
                    "ultimo_numero": 0,
                }).execute()
                numero_ct = "1"

        # 4. Montar dados
        cte_dict = {
            "numero_ct": numero_ct,
            "serie": cte.serie,
            "tipo_cte": cte.tipo_cte,
            "modal": cte.modal,
            "tipo_servico": cte.tipo_servico,
            "cfop": cte.cfop,
            "natureza_operacao": cte.natureza_operacao,
            "remetente": cte.remetente.model_dump(),
            "destinatario": cte.destinatario.model_dump(),
            "valor_total_servico": str(cte.valor_total_servico),
            "valor_receber": str(cte.valor_receber or cte.valor_total_servico),
            "aliquota_icms": str(cte.aliquota_icms),
            "valor_icms": str(cte.valor_icms),
            "carga": cte.carga.model_dump(),
            "nfe_vinculadas": [n.model_dump() for n in cte.nfe_vinculadas],
            "rodoviario": {"rntrc": cte.rntrc or empresa.get("rntrc", "")},
            "ambiente": cte.ambiente,
        }

        # 5. Autorizar
        resultado = await cte_service.autorizar_cte(
            cte_data=cte_dict,
            empresa=empresa,
            cert_bytes=cert_bytes,
            senha_cert=senha_cert,
        )

        # 6. Salvar no banco
        nota_id = None
        if resultado.get("autorizado"):
            nota_id = await _salvar_cte_banco(
                db, cte, numero_ct, resultado
            )

            # Atualizar numeração
            db.table("numeracao_fiscal").upsert({
                "empresa_id": cte.empresa_id,
                "modelo": "57",
                "serie": cte.serie,
                "ultimo_numero": int(numero_ct),
            }).execute()

        return CTeResponse(
            id=nota_id,
            autorizado=resultado.get("autorizado", False),
            chave_acesso=resultado.get("chave_acesso"),
            protocolo=resultado.get("protocolo"),
            numero_ct=numero_ct,
            serie=cte.serie,
            status_codigo=resultado.get("status_codigo"),
            status_descricao=resultado.get("status_descricao"),
            erro=resultado.get("erro"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao autorizar CT-e: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CONSULTA CT-e
# ============================================

class CTeConsultaRequest(BaseModel):
    """Request para consultar CT-e com certificado seguro"""
    certificado_senha: str = Field(
        ...,
        min_length=1,
        description="Senha do certificado A1"
    )


class CTeEventoRequest(BaseModel):
    """Request para evento de CT-e com certificado seguro"""
    certificado_senha: str = Field(
        ...,
        min_length=1,
        description="Senha do certificado A1"
    )
    motivo: str = Field(..., min_length=15, max_length=255, description="Motivo da operação")


@router.post(
    "/consultar/{chave_acesso}",
    summary="Consultar CT-e por chave de acesso",
)
async def consultar_cte(
    chave_acesso: str = Path(..., pattern=r"^\d{44}$"),
    request: CTeConsultaRequest = Body(...),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Consulta status de CT-e na SEFAZ."""
    # Buscar empresa
    nota = db.table("cte_emitidos").select(
        "empresa_id"
    ).eq("chave_acesso", chave_acesso).execute()

    if not nota.data:
        raise HTTPException(status_code=404, detail="CT-e não encontrado")

    empresa = db.table("empresas").select("*").eq(
        "id", nota.data[0]["empresa_id"]
    ).eq("usuario_id", usuario["id"]).execute()

    if not empresa.data:
        raise HTTPException(status_code=403, detail="Sem permissão")

    emp = empresa.data[0]

    cert_bytes = certificado_service.descriptografar_certificado(
        emp["certificado_a1"]
    )

    # SEGURANÇA: Senha vem do request (não do banco) para evitar exposição
    senha_cert = request.certificado_senha

    resultado = await cte_service.consultar_cte(
        chave_acesso=chave_acesso,
        uf=emp["uf"],
        cert_bytes=cert_bytes,
        senha_cert=senha_cert,
    )

    return resultado


# ============================================
# CANCELAMENTO CT-e
# ============================================

@router.post(
    "/cancelar/{chave_acesso}",
    summary="Cancelar CT-e autorizado",
)
async def cancelar_cte(
    chave_acesso: str = Path(..., pattern=r"^\d{44}$"),
    request: CTeEventoRequest = Body(...),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Cancela CT-e autorizado.

    Condições: até 168h (7 dias) após autorização, motivo mín. 15 caracteres.
    """
    nota = db.table("cte_emitidos").select("*").eq(
        "chave_acesso", chave_acesso
    ).execute()

    if not nota.data:
        raise HTTPException(status_code=404, detail="CT-e não encontrado")

    cte = nota.data[0]

    if cte["situacao"] != "autorizada":
        raise HTTPException(
            status_code=400,
            detail=f"CT-e não pode ser cancelado. Situação: {cte['situacao']}",
        )

    empresa = db.table("empresas").select("*").eq(
        "id", cte["empresa_id"]
    ).eq("usuario_id", usuario["id"]).execute()

    if not empresa.data:
        raise HTTPException(status_code=403, detail="Sem permissão")

    emp = empresa.data[0]

    cert_bytes = certificado_service.descriptografar_certificado(
        emp["certificado_a1"]
    )

    # SEGURANÇA: Senha vem do request (não do banco) para evitar exposição
    senha_cert = request.certificado_senha

    resultado = await cte_service.cancelar_cte(
        chave_acesso=chave_acesso,
        protocolo=cte.get("protocolo", ""),
        motivo=request.motivo,
        cnpj=emp["cnpj"],
        uf=emp["uf"],
        cert_bytes=cert_bytes,
        senha_cert=senha_cert,
    )

    if resultado.get("cancelado"):
        db.table("cte_emitidos").update({
            "situacao": "cancelada",
        }).eq("id", cte["id"]).execute()

    return resultado


# ============================================
# DACTE (PDF)
# ============================================

@router.get(
    "/{chave_acesso}/dacte",
    summary="Gerar DACTE (PDF)",
)
async def gerar_dacte(
    chave_acesso: str = Path(..., pattern=r"^\d{44}$"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Gera DACTE em PDF a partir do XML do CT-e."""
    nota = db.table("cte_emitidos").select("*").eq(
        "chave_acesso", chave_acesso
    ).execute()

    if not nota.data:
        raise HTTPException(status_code=404, detail="CT-e não encontrado")

    cte = nota.data[0]
    xml_content = cte.get("xml_completo")

    if not xml_content:
        raise HTTPException(
            status_code=400,
            detail="XML do CT-e não disponível para geração do DACTE",
        )

    # Validar pertence ao usuário
    empresa = db.table("empresas").select("id").eq(
        "id", cte["empresa_id"]
    ).eq("usuario_id", usuario["id"]).execute()

    if not empresa.data:
        raise HTTPException(status_code=403, detail="Sem permissão")

    from app.services.danfe_service import danfe_service
    import io

    pdf_bytes = danfe_service.gerar_dacte(xml_content)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="DACTE_{chave_acesso}.pdf"'
        },
    )


# ============================================
# LISTAGEM
# ============================================

@router.get(
    "/listar/{empresa_id}",
    response_model=List[CTeListItem],
    summary="Listar CT-e emitidos",
)
async def listar_cte(
    empresa_id: str,
    situacao: Optional[str] = Query(None),
    data_inicio: Optional[str] = Query(None, description="YYYY-MM-DD"),
    data_fim: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """Lista CT-e emitidos por uma empresa."""
    emp = db.table("empresas").select("id").eq(
        "id", empresa_id
    ).eq("usuario_id", usuario["id"]).execute()

    if not emp.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    query = db.table("cte_emitidos").select("*").eq("empresa_id", empresa_id)

    if situacao:
        query = query.eq("situacao", situacao)
    if data_inicio:
        query = query.gte("data_emissao", f"{data_inicio}T00:00:00")
    if data_fim:
        query = query.lte("data_emissao", f"{data_fim}T23:59:59")

    result = query.order("data_emissao", desc=True).range(
        offset, offset + limit - 1
    ).execute()

    return [
        CTeListItem(
            id=r["id"],
            numero_ct=r["numero_ct"],
            serie=r.get("serie", "1"),
            chave_acesso=r.get("chave_acesso"),
            situacao=r.get("situacao", "pendente"),
            rem_nome=r.get("rem_nome"),
            dest_nome=r.get("dest_nome"),
            valor_total_servico=float(r.get("valor_total_servico", 0)),
            data_emissao=r.get("data_emissao"),
            modal=r.get("modal"),
        )
        for r in (result.data or [])
    ]


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

async def _salvar_cte_banco(
    db: Client,
    cte: CTeCreate,
    numero_ct: str,
    resultado: dict,
) -> str:
    """Salva CT-e autorizado no banco."""
    data = {
        "empresa_id": cte.empresa_id,
        "numero_ct": numero_ct,
        "serie": cte.serie,
        "modelo": "57",
        "chave_acesso": resultado.get("chave_acesso", ""),
        "situacao": "autorizada",
        "protocolo": resultado.get("protocolo", ""),
        "tipo_cte": cte.tipo_cte,
        "modal": cte.modal,
        "tipo_servico": cte.tipo_servico,
        "rem_cnpj": cte.remetente.cnpj,
        "rem_nome": cte.remetente.nome,
        "rem_uf": cte.remetente.uf,
        "rem_municipio": cte.remetente.municipio,
        "dest_cnpj": cte.destinatario.cnpj,
        "dest_nome": cte.destinatario.nome,
        "dest_uf": cte.destinatario.uf,
        "dest_municipio": cte.destinatario.municipio,
        "valor_total_servico": float(cte.valor_total_servico),
        "valor_receber": float(cte.valor_receber or cte.valor_total_servico),
        "valor_icms": float(cte.valor_icms),
        "valor_carga": float(cte.carga.valor),
        "produto_predominante": cte.carga.produto_predominante,
        "cfop": cte.cfop,
        "natureza_operacao": cte.natureza_operacao,
        "nfe_vinculadas": [n.model_dump() for n in cte.nfe_vinculadas],
        "data_emissao": datetime.now().isoformat(),
        "data_autorizacao": datetime.now().isoformat(),
        "ambiente": cte.ambiente,
    }

    response = db.table("cte_emitidos").insert(data).execute()

    if not response.data:
        raise Exception("Erro ao salvar CT-e no banco")

    return response.data[0]["id"]
