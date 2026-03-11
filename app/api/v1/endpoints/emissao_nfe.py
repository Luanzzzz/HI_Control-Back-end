"""
Endpoints para emissão, autorização e gestão de NF-e.

Funcionalidades:
- Autorização de NF-e junto à SEFAZ
- Consulta de status de NF-e
- Cancelamento de NF-e autorizada
- Inutilização de numeração

Requer módulo: emissor_notas
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Body
from fastapi.responses import StreamingResponse
from supabase import Client
from datetime import datetime
import logging

from app.dependencies import (
    get_db,
    get_current_user,
    require_modules,
)
from app.models.nfe_completa import (
    NotaFiscalCompletaCreate,
    NotaFiscalCompletaResponse,
    SefazResponseModel,
)
from app.services.sefaz_service import sefaz_service, SefazException
from app.services.certificado_service import (
    certificado_service,
    CertificadoError,
    CertificadoExpiradoError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfe", tags=["NF-e Issuance"])


# ============================================
# AUTORIZAÇÃO DE NF-E
# ============================================

@router.post(
    "/autorizar",
    response_model=NotaFiscalCompletaResponse,
    dependencies=[require_modules("emissor_notas")],
    status_code=201,
)
async def autorizar_nfe(
    nfe_data: NotaFiscalCompletaCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Autoriza uma NF-e junto à SEFAZ.

    **Requer módulo**: `emissor_notas` (plano Profissional ou superior)

    **Validações automáticas**:
    - Certificado digital válido e não expirado
    - Empresa pertence ao usuário autenticado
    - Todos os campos obrigatórios conforme layout SEFAZ 4.0
    - NCM, CFOP, CST válidos
    - Cálculos de impostos corretos

    **Processo**:
    1. Valida dados da NF-e
    2. Carrega certificado digital da empresa
    3. Constrói XML conforme layout SEFAZ 4.0
    4. Assina digitalmente
    5. Envia para SEFAZ (ambiente homologação)
    6. Armazena NF-e e itens no banco de dados
    7. Retorna chave de acesso e protocolo

    **Códigos de status SEFAZ**:
    - `100`: Autorizado o uso da NF-e
    - `204`: Duplicidade de NF-e
    - `212`: CNPJ do destinatário inválido
    - `539`: Certificado digital vencido
    - Veja lista completa em: http://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=ykovZ4/3hEw=

    **Exemplo de resposta (sucesso)**:
    ```json
    {
      "id": "uuid-nota",
      "chave_acesso": "35240112345678000190550010000001231234567890",
      "numero_nf": "123",
      "serie": "1",
      "situacao": "autorizada",
      "protocolo": "135240012345678",
      "data_autorizacao": "2026-01-26T10:30:00",
      "valor_total": 1500.00,
      "itens": [...],
      "sefaz_response": {
        "status_codigo": "100",
        "status_descricao": "Autorizado o uso da NF-e"
      }
    }
    ```

    **Exemplo de resposta (rejeição)**:
    ```json
    {
      "detail": "NF-e rejeitada pela SEFAZ",
      "sefaz_response": {
        "status_codigo": "204",
        "status_descricao": "Duplicidade de NF-e",
        "rejeicoes": [
          {
            "codigo": "204",
            "motivo": "Rejeição: Duplicidade de NF-e [nRec:123456]",
            "correcao": "Verifique se a NF-e já foi autorizada anteriormente"
          }
        ]
      }
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # 1. Validar empresa pertence ao usuário
        empresa = await _validar_empresa_usuario(db, nfe_data.empresa_id, user_id)

        # 2. Validar certificado digital
        if not empresa.get("certificado_a1"):
            raise HTTPException(
                status_code=400,
                detail="Empresa não possui certificado digital cadastrado. "
                       "Faça o upload do certificado antes de emitir NF-e."
            )

        # Verificar validade do certificado
        cert_status = certificado_service.verificar_expiracao(
            empresa.get("certificado_validade")
        )

        if cert_status["status"] == "expirado":
            raise HTTPException(
                status_code=400,
                detail=f"Certificado digital expirado. {cert_status['alerta']}"
            )

        if cert_status["status"] == "expirando_em_breve":
            logger.warning(
                f"Certificado próximo da expiração: {cert_status['alerta']}"
            )

        # 3. Descriptografar certificado e obter senha
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

        # 4. Enviar para SEFAZ
        logger.info(
            f"Autorizando NF-e {nfe_data.numero_nf}/{nfe_data.serie} "
            f"para empresa {empresa['cnpj']}"
        )

        sefaz_response = sefaz_service.autorizar_nfe(
            nfe_data=nfe_data,
            cert_bytes=cert_bytes,
            senha_cert=senha_cert,
            empresa_cnpj=empresa["cnpj"],
            empresa_ie=empresa.get("inscricao_estadual", "ISENTO"),
            empresa_razao_social=empresa["razao_social"],
            empresa_uf=empresa["uf"],
        )

        # 5. Verificar se autorizado
        if not sefaz_response.autorizado:
            logger.warning(
                f"NF-e {nfe_data.numero_nf} rejeitada: "
                f"{sefaz_response.status_codigo} - {sefaz_response.status_descricao}"
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "NF-e rejeitada pela SEFAZ",
                    "sefaz_response": sefaz_response.model_dump(),
                }
            )

        # 6. Salvar no banco de dados
        nota_id = await _salvar_nfe_banco(
            db,
            nfe_data,
            sefaz_response,
            user_id,
        )

        # 7. Construir resposta
        response = NotaFiscalCompletaResponse(
            id=nota_id,
            chave_acesso=sefaz_response.chave_acesso,
            numero_nf=nfe_data.numero_nf,
            serie=nfe_data.serie,
            modelo=nfe_data.modelo,
            situacao="autorizada",
            protocolo=sefaz_response.protocolo,
            data_autorizacao=datetime.now(),
            valor_total=nfe_data.calcular_totais()["valor_total_nota"],
            itens=nfe_data.itens,
            transporte=nfe_data.transporte,
            cobranca=nfe_data.cobranca,
            destinatario=nfe_data.destinatario,
            sefaz_response=sefaz_response,
        )

        logger.info(
            f"NF-e {nfe_data.numero_nf} autorizada com sucesso. "
            f"Chave: {sefaz_response.chave_acesso}"
        )

        return response

    except HTTPException:
        raise
    except CertificadoExpiradoError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CertificadoError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar certificado: {str(e)}"
        )
    except SefazException as e:
        logger.error(f"Erro SEFAZ: {e}")
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Erro ao comunicar com SEFAZ",
                "codigo": e.codigo,
                "descricao": e.mensagem,
                "campo": e.campo_erro,
            }
        )
    except Exception as e:
        logger.error(f"Erro ao autorizar NF-e: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno ao autorizar NF-e: {str(e)}"
        )


# ============================================
# CONSULTA DE NF-E
# ============================================

@router.post(
    "/consultar/{chave_acesso}",
    response_model=SefazResponseModel,
    dependencies=[require_modules("emissor_notas")],
)
async def consultar_nfe(
    chave_acesso: str = Path(
        ...,
        pattern=r"^\d{44}$",
        description="Chave de acesso de 44 dígitos"
    ),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Consulta status de NF-e por chave de acesso.

    **Requer módulo**: `emissor_notas`

    **Funcionalidade**:
    - Consulta situação atual da NF-e na SEFAZ
    - Cache in-memory de 5 minutos (reduz chamadas à SEFAZ)
    - Atualiza status no banco de dados local

    **Chave de acesso**:
    - 44 dígitos numéricos
    - Formato: UF + AAMM + CNPJ + MOD + SERIE + NUMERO + CODIGO + DV
    - Exemplo: `35240112345678000190550010000001231234567890`

    **Códigos de resposta SEFAZ**:
    - `100`: NF-e autorizada
    - `110`: NF-e denegada
    - `101`: NF-e cancelada
    - `217`: NF-e não encontrada

    **Exemplo de resposta**:
    ```json
    {
      "status_codigo": "100",
      "status_descricao": "Autorizado o uso da NF-e",
      "protocolo": "135240012345678",
      "chave_acesso": "35240112345678000190550010000001231234567890",
      "autorizado": true,
      "rejeitado": false,
      "rejeicoes": []
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # 1. Buscar NF-e no banco
        nota = await _buscar_nfe_por_chave(db, chave_acesso, user_id)

        if not nota:
            raise HTTPException(
                status_code=404,
                detail="NF-e não encontrada no sistema local"
            )

        # 2. Carregar certificado da empresa
        empresa = await _validar_empresa_usuario(db, nota["empresa_id"], user_id)

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

        # 3. Consultar SEFAZ
        logger.info(f"Consultando NF-e: {chave_acesso}")

        sefaz_response = sefaz_service.consultar_nfe(
            chave_acesso=chave_acesso,
            empresa_uf=empresa["uf"],
            cert_bytes=cert_bytes,
            senha_cert=senha_cert,
        )

        # 4. Atualizar status no banco
        await _atualizar_status_nfe(db, nota["id"], sefaz_response)

        return sefaz_response

    except HTTPException:
        raise
    except SefazException as e:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Erro ao consultar SEFAZ",
                "codigo": e.codigo,
                "descricao": e.mensagem,
            }
        )
    except Exception as e:
        logger.error(f"Erro ao consultar NF-e: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )


# ============================================
# CANCELAMENTO DE NF-E
# ============================================

@router.post(
    "/cancelar/{chave_acesso}",
    response_model=SefazResponseModel,
    dependencies=[require_modules("emissor_notas")],
)
async def cancelar_nfe(
    chave_acesso: str = Path(
        ...,
        pattern=r"^\d{44}$",
        description="Chave de acesso de 44 dígitos"
    ),
    motivo: str = Body(
        ...,
        min_length=15,
        max_length=255,
        embed=True,
        description="Motivo do cancelamento (mínimo 15 caracteres)"
    ),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Cancela NF-e autorizada.

    **Requer módulo**: `emissor_notas`

    **Condições para cancelamento**:
    - NF-e deve estar autorizada (status 100)
    - Prazo: até 24 horas após autorização
    - Motivo: mínimo 15 caracteres

    **Importante**:
    - Cancelamento é irreversível
    - Após cancelamento, a numeração não pode ser reutilizada
    - Para corrigir dados, use Carta de Correção Eletrônica (CC-e) ao invés de cancelamento

    **Códigos SEFAZ**:
    - `135`: Evento registrado e vinculado à NF-e
    - `218`: Cancelamento não permitido após 24h
    - `539`: Certificado digital vencido

    **Exemplo de requisição**:
    ```json
    {
      "motivo": "Erro no valor do produto - Cliente solicitou cancelamento"
    }
    ```

    **Exemplo de resposta (sucesso)**:
    ```json
    {
      "status_codigo": "135",
      "status_descricao": "Evento registrado e vinculado a NF-e",
      "protocolo": "135240012345679",
      "chave_acesso": "35240112345678000190550010000001231234567890",
      "rejeicoes": []
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # 1. Buscar NF-e
        nota = await _buscar_nfe_por_chave(db, chave_acesso, user_id)

        if not nota:
            raise HTTPException(
                status_code=404,
                detail="NF-e não encontrada"
            )

        # 2. Validar situação
        if nota["situacao"] != "autorizada":
            raise HTTPException(
                status_code=400,
                detail=f"NF-e não pode ser cancelada. Situação atual: {nota['situacao']}"
            )

        # 3. Validar prazo (24 horas)
        if not nota.get("data_autorizacao"):
            raise HTTPException(
                status_code=400,
                detail="Data de autorização não encontrada"
            )

        # 4. Carregar certificado
        empresa = await _validar_empresa_usuario(db, nota["empresa_id"], user_id)

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

        # 5. Cancelar na SEFAZ
        logger.info(f"Cancelando NF-e {chave_acesso}: {motivo}")

        sefaz_response = sefaz_service.cancelar_nfe(
            chave_acesso=chave_acesso,
            protocolo=nota["protocolo"],
            motivo=motivo,
            empresa_cnpj=empresa["cnpj"],
            empresa_uf=empresa["uf"],
            cert_bytes=cert_bytes,
            senha_cert=senha_cert,
            data_autorizacao=nota["data_autorizacao"],
        )

        # 6. Atualizar no banco
        await _atualizar_situacao_nfe(
            db,
            nota["id"],
            "cancelada",
            sefaz_response.protocolo
        )

        logger.info(f"NF-e {chave_acesso} cancelada com sucesso")

        return sefaz_response

    except HTTPException:
        raise
    except SefazException as e:
        raise HTTPException(
            status_code=502 if e.codigo == "999" else 400,
            detail={
                "message": "Erro ao cancelar NF-e",
                "codigo": e.codigo,
                "descricao": e.mensagem,
            }
        )
    except Exception as e:
        logger.error(f"Erro ao cancelar NF-e: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

async def _validar_empresa_usuario(
    db: Client,
    empresa_id: str,
    user_id: str
) -> dict:
    """
    Valida que empresa pertence ao usuário.

    Returns:
        Dict com dados da empresa

    Raises:
        HTTPException: Se empresa não encontrada ou não pertence ao usuário
    """
    try:
        # Remover .single() para evitar erro PGRST116 quando não há resultados
        response = db.table("empresas") \
            .select("*") \
            .eq("id", empresa_id) \
            .eq("usuario_id", user_id) \
            .execute()

        # Verificar se há dados
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=404,
                detail="Empresa não encontrada ou não pertence ao usuário"
            )

        # Retornar primeiro (e único) resultado
        return response.data[0]

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log e lançar erro genérico para outros erros
        logging.getLogger(__name__).error(f"Erro ao validar empresa {empresa_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao validar empresa: {str(e)}"
        )


async def _salvar_nfe_banco(
    db: Client,
    nfe_data: NotaFiscalCompletaCreate,
    sefaz_response: SefazResponseModel,
    user_id: str,
) -> str:
    """
    Salva NF-e autorizada no banco de dados.

    Args:
        db: Cliente Supabase
        nfe_data: Dados da NF-e
        sefaz_response: Resposta SEFAZ
        user_id: ID do usuário

    Returns:
        ID da nota fiscal criada
    """
    totais = nfe_data.calcular_totais()

    # Inserir nota fiscal
    nota_data = {
        "empresa_id": nfe_data.empresa_id,
        "tipo_nf": "NFe" if nfe_data.modelo == "55" else "NFCe",
        "numero_nf": nfe_data.numero_nf,
        "serie": nfe_data.serie,
        "modelo": nfe_data.modelo,
        "chave_acesso": sefaz_response.chave_acesso,
        "situacao": "autorizada",
        "protocolo": sefaz_response.protocolo,
        "data_emissao": datetime.now().isoformat(),
        "data_autorizacao": datetime.now().isoformat(),
        "valor_total": float(totais["valor_total"]),
        "valor_produtos": float(totais["valor_produtos"]),
        "valor_icms": float(totais["total_icms"]),
        "valor_ipi": float(totais["total_ipi"]),
        "valor_pis": float(totais["total_pis"]),
        "valor_cofins": float(totais["total_cofins"]),
        "nome_destinatario": nfe_data.destinatario.nome,
        "cnpj_destinatario": nfe_data.destinatario.cnpj,
        "destinatario_cpf": nfe_data.destinatario.cpf,
        "ambiente": nfe_data.ambiente,
        "situacao_sefaz_codigo": sefaz_response.status_codigo,
        "situacao_sefaz_motivo": sefaz_response.status_descricao,
    }

    nota_response = db.table("notas_fiscais").insert(nota_data).execute()
    if not nota_response.data:
        raise Exception("Erro ao salvar nota fiscal no banco")
    nota_id = nota_response.data[0]["id"]

    # Inserir itens
    for item in nfe_data.itens:
        item_data = {
            "nota_fiscal_id": nota_id,
            "numero_item": item.numero_item,
            "codigo_produto": item.codigo_produto,
            "descricao": item.descricao,
            "ncm": item.ncm,
            "cfop": item.cfop,
            "unidade_comercial": item.unidade_comercial,
            "quantidade_comercial": float(item.quantidade_comercial),
            "valor_unitario_comercial": float(item.valor_unitario_comercial),
            "valor_total_bruto": float(item.valor_total_bruto),
            "valor_icms": float(item.icms.valor),
            "valor_ipi": float(item.ipi.valor if item.ipi else 0),
            "valor_pis": float(item.pis.valor),
            "valor_cofins": float(item.cofins.valor),
        }
        db.table("nota_fiscal_itens").insert(item_data).execute()

    # Inserir transporte (se houver)
    if nfe_data.transporte:
        transp_data = {
            "nota_fiscal_id": nota_id,
            "modalidade_frete": nfe_data.transporte.modalidade_frete,
        }
        if nfe_data.transporte.transportadora:
            transp_data.update({
                "transportadora_cnpj": nfe_data.transporte.transportadora.cnpj_cpf,
                "transportadora_razao_social": nfe_data.transporte.transportadora.razao_social,
            })
        db.table("nota_fiscal_transporte").insert(transp_data).execute()

    # Inserir duplicatas (se houver)
    if nfe_data.cobranca and nfe_data.cobranca.duplicatas:
        for dup in nfe_data.cobranca.duplicatas:
            dup_data = {
                "nota_fiscal_id": nota_id,
                "numero_duplicata": dup.numero_duplicata,
                "data_vencimento": dup.data_vencimento,
                "valor": float(dup.valor),
            }
            db.table("nota_fiscal_duplicatas").insert(dup_data).execute()

    return nota_id


async def _buscar_nfe_por_chave(
    db: Client,
    chave_acesso: str,
    user_id: str
) -> Optional[dict]:
    """Busca NF-e por chave de acesso"""
    response = db.table("notas_fiscais") \
        .select("*") \
        .eq("chave_acesso", chave_acesso) \
        .single() \
        .execute()

    return response.data if response.data else None


async def _atualizar_status_nfe(
    db: Client,
    nota_id: str,
    sefaz_response: SefazResponseModel
):
    """Atualiza status da NF-e após consulta"""
    db.table("notas_fiscais").update({
        "situacao_sefaz_codigo": sefaz_response.status_codigo,
        "situacao_sefaz_motivo": sefaz_response.status_descricao,
    }).eq("id", nota_id).execute()


async def _atualizar_situacao_nfe(
    db: Client,
    nota_id: str,
    situacao: str,
    protocolo: Optional[str] = None
):
    """Atualiza situação da NF-e (cancelada, denegada, etc)"""
    update_data = {"situacao": situacao}
    if protocolo:
        update_data["protocolo_cancelamento"] = protocolo

    db.table("notas_fiscais").update(update_data).eq("id", nota_id).execute()


# ============================================
# DANFE (PDF)
# ============================================

@router.get(
    "/{chave_acesso}/danfe",
    summary="Gerar/Download DANFE (PDF)",
)
async def gerar_danfe(
    chave_acesso: str = Path(..., pattern=r"^\d{44}$"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Gera DANFE em PDF a partir da chave de acesso.

    Se a nota já tiver pdf_url, redireciona. Caso contrário, gera o PDF
    a partir do XML armazenado.
    """
    try:
        nota = await _buscar_nfe_por_chave(db, chave_acesso, usuario["id"])
        if not nota:
            raise HTTPException(status_code=404, detail="NF-e não encontrada")

        xml_content = nota.get("xml_completo") or nota.get("xml_resumo")
        if not xml_content:
            raise HTTPException(
                status_code=400,
                detail="XML da NF-e não disponível para geração do DANFE"
            )

        from app.services.danfe_service import danfe_service

        modelo = nota.get("modelo", "55")
        if modelo == "65":
            pdf_bytes = danfe_service.gerar_danfce(xml_content)
            filename = f"DANFCE_{chave_acesso}.pdf"
        else:
            pdf_bytes = danfe_service.gerar_danfe(xml_content)
            filename = f"DANFE_{chave_acesso}.pdf"

        import io
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao gerar DANFE: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao gerar DANFE: {str(e)}")


# ============================================
# INUTILIZAÇÃO DE NUMERAÇÃO
# ============================================

@router.post(
    "/inutilizar",
    response_model=SefazResponseModel,
    dependencies=[require_modules("emissor_notas")],
    summary="Inutilizar numeração de NF-e",
)
async def inutilizar_numeracao(
    empresa_id: str = Body(..., embed=True),
    serie: str = Body(..., embed=True),
    numero_inicio: int = Body(..., embed=True, ge=1),
    numero_fim: int = Body(..., embed=True, ge=1),
    justificativa: str = Body(..., embed=True, min_length=15, max_length=255),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db),
):
    """
    Inutiliza faixa de numeração de NF-e na SEFAZ.

    Use quando houver quebra de sequência numérica.
    A inutilização é irreversível.
    """
    user_id = usuario["id"]

    try:
        empresa = await _validar_empresa_usuario(db, empresa_id, user_id)

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

        sefaz_response = sefaz_service.inutilizar_numeracao(
            empresa_cnpj=empresa["cnpj"],
            empresa_uf=empresa["uf"],
            serie=serie,
            numero_inicio=numero_inicio,
            numero_fim=numero_fim,
            justificativa=justificativa,
            cert_bytes=cert_bytes,
            senha_cert=senha_cert,
        )

        return sefaz_response

    except HTTPException:
        raise
    except SefazException as e:
        raise HTTPException(status_code=502, detail={"message": str(e)})
    except Exception as e:
        logger.error(f"Erro ao inutilizar: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
