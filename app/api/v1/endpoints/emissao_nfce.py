"""
Endpoints para emissão de NFC-e (Nota Fiscal de Consumidor Eletrônica - Modelo 65).

Diferenças em relação à NF-e:
- Modelo 65 (não 55)
- QR Code obrigatório
- CSC (Código de Segurança do Contribuinte) obrigatório
- Destinatário opcional
- DANFCE formato cupom
"""
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from supabase import Client
from datetime import datetime
from decimal import Decimal
import logging

from app.dependencies import get_db, get_current_user, require_modules
from app.services.nfce_service import nfce_service
from app.services.certificado_service import certificado_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfce", tags=["NFC-e - Consumidor"])


# ============================================
# SCHEMAS
# ============================================

class NFCeItemCreate(BaseModel):
    """Item da NFC-e."""
    codigo_produto: str = Field(..., description="Código do produto")
    descricao: str = Field(..., max_length=120, description="Descrição do produto")
    ncm: str = Field(..., pattern=r"^\d{8}$", description="NCM (8 dígitos)")
    cfop: str = Field(..., pattern=r"^\d{4}$", description="CFOP (4 dígitos)")
    unidade: str = Field(default="UN", max_length=6)
    quantidade: Decimal = Field(..., gt=0)
    valor_unitario: Decimal = Field(..., gt=0)
    valor_total: Decimal = Field(..., gt=0)

    # Impostos simplificados
    cst_icms: str = Field(default="00", description="CST ICMS")
    aliquota_icms: Decimal = Field(default=Decimal("0"))
    valor_icms: Decimal = Field(default=Decimal("0"))


class NFCeDestinatarioCreate(BaseModel):
    """Destinatário opcional da NFC-e."""
    cpf: Optional[str] = Field(None, pattern=r"^\d{11}$")
    cnpj: Optional[str] = Field(None, pattern=r"^\d{14}$")
    nome: Optional[str] = Field(None, max_length=60)


class NFCeCreate(BaseModel):
    """Dados para emissão de NFC-e."""
    empresa_id: str = Field(..., description="ID da empresa emitente")
    serie: str = Field(default="1", max_length=3)
    numero_nf: Optional[str] = Field(
        None, description="Número da NFC-e (auto-incremento se vazio)"
    )
    natureza_operacao: str = Field(
        default="VENDA AO CONSUMIDOR FINAL",
        max_length=60,
    )
    forma_pagamento: str = Field(
        default="01",
        description="01=Dinheiro, 02=Cheque, 03=Cartão Crédito, "
                    "04=Cartão Débito, 05=Crédito Loja, 10=VA, "
                    "11=VR, 12=PIX, 99=Outros",
    )
    valor_pagamento: Optional[Decimal] = Field(
        None, description="Valor pago (se vazio, usa total)"
    )
    troco: Decimal = Field(default=Decimal("0"))
    destinatario: Optional[NFCeDestinatarioCreate] = None
    itens: list[NFCeItemCreate] = Field(..., min_length=1)
    info_complementar: Optional[str] = Field(None, max_length=2000)
    ambiente: str = Field(
        default="2",
        description="1=Produção, 2=Homologação",
    )


class NFCeResponse(BaseModel):
    """Resposta da emissão de NFC-e."""
    id: Optional[str] = None
    autorizado: bool
    chave_acesso: Optional[str] = None
    protocolo: Optional[str] = None
    qrcode_url: Optional[str] = None
    numero_nf: Optional[str] = None
    serie: Optional[str] = None
    status_codigo: Optional[str] = None
    status_descricao: Optional[str] = None
    rejeicoes: Optional[list] = None
    erro: Optional[str] = None


# ============================================
# AUTORIZAÇÃO NFC-e
# ============================================

@router.post(
    "/autorizar",
    response_model=NFCeResponse,
    dependencies=[require_modules("emissor_notas")],
    status_code=201,
    summary="Autorizar NFC-e (modelo 65)",
)
async def autorizar_nfce(
    nfce: NFCeCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Autoriza uma NFC-e (modelo 65) junto à SEFAZ.

    **Diferenças da NF-e**:
    - QR Code obrigatório (gerado automaticamente)
    - CSC necessário (configurar via PUT /empresas/{id})
    - Destinatário é opcional
    - Formato DANFCE (cupom)

    **Pagamento**:
    - `forma_pagamento`: código do meio de pagamento
    - `valor_pagamento`: valor recebido
    - `troco`: valor do troco

    **Numeração**: Se `numero_nf` for vazio, usa auto-incremento.
    """
    user_id = usuario["id"]

    try:
        # 1. Validar empresa
        result = db.table("empresas").select("*").eq(
            "id", nfce.empresa_id
        ).eq("usuario_id", user_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")

        empresa = result.data[0]

        # 2. Validar CSC
        if not empresa.get("csc_id") or not empresa.get("csc_token"):
            raise HTTPException(
                status_code=400,
                detail="CSC (Código de Segurança do Contribuinte) não configurado. "
                       "Configure via PUT /empresas/{id} com csc_id e csc_token.",
            )

        # 3. Validar certificado
        if not empresa.get("certificado_a1"):
            raise HTTPException(
                status_code=400,
                detail="Certificado digital não cadastrado.",
            )

        cert_status = certificado_service.verificar_expiracao(
            empresa.get("certificado_validade")
        )
        if cert_status["status"] == "expirado":
            raise HTTPException(
                status_code=400,
                detail=f"Certificado expirado. {cert_status['alerta']}",
            )

        cert_bytes = certificado_service.descriptografar_certificado(
            empresa["certificado_a1"]
        )
        senha_encrypted = empresa.get("certificado_senha_encrypted")
        if not senha_encrypted:
            raise HTTPException(
                status_code=400,
                detail="Senha do certificado não configurada. Faça o reupload do certificado."
            )
        senha_cert = certificado_service.descriptografar_senha(senha_encrypted)

        # 4. Auto-incremento de numeração
        numero_nf = nfce.numero_nf
        if not numero_nf:
            numero_nf = await _proximo_numero(db, nfce.empresa_id, "65", nfce.serie)

        # 5. Montar dados
        nfce_dict = {
            "numero_nf": numero_nf,
            "serie": nfce.serie,
            "modelo": "65",
            "natureza_operacao": nfce.natureza_operacao,
            "ambiente": nfce.ambiente,
            "forma_pagamento": nfce.forma_pagamento,
            "valor_pagamento": float(nfce.valor_pagamento or sum(
                i.valor_total for i in nfce.itens
            )),
            "troco": float(nfce.troco),
            "itens": [item.model_dump() for item in nfce.itens],
            "destinatario": nfce.destinatario.model_dump() if nfce.destinatario else None,
            "info_complementar": nfce.info_complementar,
        }

        # 6. Autorizar
        resultado = await nfce_service.autorizar_nfce(
            nfce_data=nfce_dict,
            empresa=empresa,
            cert_bytes=cert_bytes,
            senha_cert=senha_cert,
        )

        # 7. Salvar no banco se autorizado
        nota_id = None
        if resultado.get("autorizado"):
            nota_id = await _salvar_nfce_banco(
                db, nfce, numero_nf, resultado, user_id
            )

            # Atualizar numeração
            await _atualizar_numeracao(
                db, nfce.empresa_id, "65", nfce.serie, int(numero_nf)
            )

        return NFCeResponse(
            id=nota_id,
            autorizado=resultado.get("autorizado", False),
            chave_acesso=resultado.get("chave_acesso"),
            protocolo=resultado.get("protocolo"),
            qrcode_url=resultado.get("qrcode_url"),
            numero_nf=numero_nf,
            serie=nfce.serie,
            status_codigo=resultado.get("status_codigo"),
            status_descricao=resultado.get("status_descricao"),
            rejeicoes=resultado.get("rejeicoes"),
            erro=resultado.get("erro"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao autorizar NFC-e: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# DANFCE (PDF)
# ============================================

@router.get(
    "/{chave_acesso}/danfce",
    summary="Gerar DANFCE (PDF cupom)",
)
async def gerar_danfce(
    chave_acesso: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Gera DANFCE em PDF (formato cupom) com QR Code.
    """
    try:
        result = db.table("notas_fiscais").select("*").eq(
            "chave_acesso", chave_acesso
        ).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="NFC-e não encontrada")

        nota = result.data[0]
        xml_content = nota.get("xml_completo") or nota.get("xml_resumo")

        if not xml_content:
            raise HTTPException(
                status_code=400,
                detail="XML da NFC-e não disponível",
            )

        # Gerar QR Code URL
        empresa_result = db.table("empresas").select(
            "csc_id, csc_token, uf"
        ).eq("id", nota["empresa_id"]).execute()

        qr_url = ""
        if empresa_result.data:
            emp = empresa_result.data[0]
            qr_url = nfce_service.gerar_qrcode_nfce(
                chave_acesso=chave_acesso,
                ambiente=nota.get("ambiente", "2"),
                csc_id=emp.get("csc_id", ""),
                csc_token=emp.get("csc_token", ""),
                uf=emp.get("uf", "SP"),
            )

        from app.services.danfe_service import danfe_service
        import io

        pdf_bytes = danfe_service.gerar_danfce(xml_content, qr_code_url=qr_url)

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="DANFCE_{chave_acesso}.pdf"'
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar DANFCE: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================
# CONFIGURAR CSC
# ============================================

@router.put(
    "/csc/{empresa_id}",
    summary="Configurar CSC da empresa para NFC-e",
)
async def configurar_csc(
    empresa_id: str,
    csc_id: str = Body(..., embed=True, description="ID do CSC (1 ou 2)"),
    csc_token: str = Body(
        ..., embed=True, description="Token CSC fornecido pela SEFAZ"
    ),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Configura CSC (Código de Segurança do Contribuinte) para NFC-e.

    O CSC é gerado no portal da SEFAZ do estado e é obrigatório
    para emissão de NFC-e. Cada empresa pode ter até 2 CSCs ativos.
    """
    user_id = usuario["id"]

    result = db.table("empresas").select("id").eq(
        "id", empresa_id
    ).eq("usuario_id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    db.table("empresas").update({
        "csc_id": csc_id,
        "csc_token": csc_token,
    }).eq("id", empresa_id).execute()

    return {"mensagem": "CSC configurado com sucesso", "empresa_id": empresa_id}


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

async def _proximo_numero(
    db: Client, empresa_id: str, modelo: str, serie: str
) -> str:
    """Obtém próximo número de NFC-e."""
    result = db.table("numeracao_fiscal").select("ultimo_numero").eq(
        "empresa_id", empresa_id
    ).eq("modelo", modelo).eq("serie", serie).execute()

    if result.data:
        return str(result.data[0]["ultimo_numero"] + 1)

    # Criar registro inicial
    db.table("numeracao_fiscal").insert({
        "empresa_id": empresa_id,
        "modelo": modelo,
        "serie": serie,
        "ultimo_numero": 0,
    }).execute()
    return "1"


async def _atualizar_numeracao(
    db: Client, empresa_id: str, modelo: str, serie: str, numero: int
):
    """Atualiza último número utilizado."""
    db.table("numeracao_fiscal").update({
        "ultimo_numero": numero,
    }).eq("empresa_id", empresa_id).eq(
        "modelo", modelo
    ).eq("serie", serie).execute()


async def _salvar_nfce_banco(
    db: Client,
    nfce: NFCeCreate,
    numero_nf: str,
    resultado: dict,
    user_id: str,
) -> str:
    """Salva NFC-e autorizada no banco."""
    valor_total = float(sum(i.valor_total for i in nfce.itens))

    nota_data = {
        "empresa_id": nfce.empresa_id,
        "tipo_nf": "NFCe",
        "numero_nf": numero_nf,
        "serie": nfce.serie,
        "modelo": "65",
        "chave_acesso": resultado.get("chave_acesso", ""),
        "situacao": "autorizada",
        "protocolo": resultado.get("protocolo", ""),
        "data_emissao": datetime.now().isoformat(),
        "data_autorizacao": datetime.now().isoformat(),
        "valor_total": valor_total,
        "nome_destinatario": (
            nfce.destinatario.nome if nfce.destinatario else "CONSUMIDOR"
        ),
        "cnpj_destinatario": (
            nfce.destinatario.cnpj if nfce.destinatario else None
        ),
        "destinatario_cpf": (
            nfce.destinatario.cpf if nfce.destinatario else None
        ),
        "ambiente": nfce.ambiente,
        "situacao_sefaz_codigo": resultado.get("status_codigo"),
        "situacao_sefaz_motivo": resultado.get("status_descricao"),
    }

    response = db.table("notas_fiscais").insert(nota_data).execute()
    if not response.data:
        raise Exception("Erro ao salvar NFC-e no banco")

    return response.data[0]["id"]
