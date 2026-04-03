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
from pydantic import BaseModel, Field
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
from app.utils.emission_guard import verificar_permissao_emissao, EmissionBlockedError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nfe", tags=["NF-e Issuance"])


# ============================================
# SCHEMAS DE SEGURANÇA
# ============================================

class NFeSenhaRequest(BaseModel):
    """Request que inclui senha do certificado para operações seguras"""
    certificado_senha: str = Field(
        ...,
        min_length=1,
        description="Senha do certificado A1"
    )


class NFeCancelamentoRequest(NFeSenhaRequest):
    """Request para cancelamento de NF-e"""
    motivo: str = Field(
        ...,
        min_length=15,
        max_length=255,
        description="Motivo do cancelamento (mín. 15 caracteres)"
    )


class NFeInutilizacaoRequest(NFeSenhaRequest):
    """Request para inutilização de numeração"""
    empresa_id: str = Field(..., description="UUID da empresa")
    serie: str = Field(..., pattern=r'^\d{1,3}$', description="Série (1-999)")
    numero_inicio: int = Field(..., ge=1, description="Número inicial")
    numero_fim: int = Field(..., ge=1, description="Número final")
    justificativa: str = Field(
        ...,
        min_length=15,
        max_length=255,
        description="Motivo da inutilização (mín. 15 caracteres)"
    )


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
        # 1. Verificar permissão de emissão em produção
        verificar_permissao_emissao(
            empresa_id=nfe_data.empresa_id,
            tipo_documento="NFe",
            raise_on_block=True
        )

        # 2. Validar empresa pertence ao usuário
        empresa = await _validar_empresa_usuario(db, nfe_data.empresa_id, user_id)

        # 2.5. Verificar duplicidade pré-emissão (idempotência)
        duplicata_existe, nota_existente = await _verificar_duplicidade_nfe(
            db, nfe_data.empresa_id, nfe_data.numero_nf, nfe_data.serie
        )
        if duplicata_existe:
            logger.warning(
                f"Tentativa de emitir NF-e duplicada: "
                f"{nfe_data.numero_nf}/{nfe_data.serie} "
                f"(chave_acesso={nota_existente.get('chave_acesso')})"
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "NF-e com este número e série já foi emitida.",
                    "chave_acesso": nota_existente.get("chave_acesso"),
                    "status": nota_existente.get("situacao", "desconhecida"),
                }
            )

        # 3. Validar certificado digital
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

        # 4. Descriptografar certificado e obter senha
        # SEGURANÇA: Senha vem do request (não do banco) para evitar exposição
        cert_bytes = certificado_service.descriptografar_certificado(
            empresa["certificado_a1"]
        )

        # SEGURANÇA: Senha fornecida no request, não recuperada do banco
        senha_cert = nfe_data.certificado_senha

        # 5. Enviar para SEFAZ
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

        # 6. Verificar se autorizado
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

        # 7. Salvar no banco de dados com tratamento crítico para falha
        try:
            nota_id = await _salvar_nfe_banco(
                db,
                nfe_data,
                sefaz_response,
                user_id,
            )
        except Exception as e:
            # SITUAÇÃO CRÍTICA: NF-e foi autorizada pelo SEFAZ mas não conseguimos
            # salvar no banco local. Logs com todos os dados para recuperação manual.
            logger.critical(
                "FALHA CRÍTICA: NF-e autorizada pelo SEFAZ mas não salva no banco. "
                "Dados para recuperação manual: "
                f"chave_acesso={sefaz_response.chave_acesso}, "
                f"protocolo={sefaz_response.protocolo}, "
                f"empresa_id={nfe_data.empresa_id}, "
                f"numero_nf={nfe_data.numero_nf}, "
                f"serie={nfe_data.serie}, "
                f"erro={str(e)}",
                exc_info=True
            )
            # Retornar 207 Multi-Status: autorizado mas não salvo localmente
            raise HTTPException(
                status_code=207,
                detail={
                    "message": "NF-e autorizada pelo SEFAZ mas houve falha ao salvar localmente. "
                              "Entre em contato com suporte com os dados de recuperação.",
                    "chave_acesso": sefaz_response.chave_acesso,
                    "protocolo": sefaz_response.protocolo,
                    "autorizado": True,
                    "salvo_localmente": False,
                }
            )

        # 8. Construir resposta
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
    except EmissionBlockedError as e:
        logger.error(f"Emissão bloqueada por segurança: {e}")
        raise HTTPException(
            status_code=403,
            detail="Emissão bloqueada por configuração de segurança. " \
                   "Verifique as variáveis SEFAZ_AMBIENTE e ALLOW_PRODUCTION_EMISSION."
        )
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
    request: NFeSenhaRequest = Body(...),
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

        # SEGURANÇA: Senha vem do request (não do banco) para evitar exposição
        senha_cert = request.certificado_senha

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
    request: NFeCancelamentoRequest = Body(...),
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

        # SEGURANÇA: Senha vem do request (não do banco) para evitar exposição
        senha_cert = request.certificado_senha

        # 5. Cancelar na SEFAZ
        logger.info(f"Cancelando NF-e {chave_acesso}: {request.motivo}")

        sefaz_response = sefaz_service.cancelar_nfe(
            chave_acesso=chave_acesso,
            protocolo=nota["protocolo"],
            motivo=request.motivo,
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

async def _verificar_duplicidade_nfe(
    db: Client,
    empresa_id: str,
    numero: int,
    serie: str
) -> tuple[bool, Optional[dict]]:
    """
    Verifica se já existe uma NF-e com o mesmo número/série para esta empresa.

    Returns:
        Tupla (existe_duplicata, dados_nota_existente)
        - existe_duplicata: True se já existe uma nota com este número/série
        - dados_nota_existente: Dados da nota existente ou None

    Raises:
        HTTPException: Se erro na consulta ao banco
    """
    try:
        result = db.table("notas_fiscais") \
            .select("id, chave_acesso, status, situacao") \
            .eq("empresa_id", empresa_id) \
            .eq("numero_nf", numero) \
            .eq("serie", serie) \
            .execute()

        if result.data and len(result.data) > 0:
            return True, result.data[0]
        return False, None

    except Exception as e:
        logging.getLogger(__name__).error(
            f"Erro ao verificar duplicidade de NF-e: {str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao verificar duplicidade: {str(e)}"
        )


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
    """
    Busca NF-e por chave de acesso.

    ✅ VALIDAÇÃO DE SEGURANÇA:
    Verifica se a nota pertence a uma empresa do usuário autenticado.
    """
    response = db.table("notas_fiscais") \
        .select("*") \
        .eq("chave_acesso", chave_acesso) \
        .single() \
        .execute()

    if not response.data:
        return None

    nota = response.data

    # ✅ Validar que nota pertence ao usuário autenticado
    empresa_result = db.table("empresas").select("usuario_id").eq(
        "id", nota["empresa_id"]
    ).execute()

    if not empresa_result.data:
        logger.error(f"Empresa {nota['empresa_id']} da nota {chave_acesso} não encontrada")
        return None

    empresa = empresa_result.data[0]

    # Se empresa não pertence ao usuário, retornar None (não encontrada)
    if empresa["usuario_id"] != user_id:
        logger.warning(
            f"🚨 Tentativa de acesso não autorizado: "
            f"user={user_id} tentou acessar nota da empresa={nota['empresa_id']}"
        )
        return None

    return nota


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
    request: NFeInutilizacaoRequest = Body(...),
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
        # Verificar permissão de emissão em produção
        verificar_permissao_emissao(
            empresa_id=request.empresa_id,
            tipo_documento="NFe",
            raise_on_block=True
        )

        empresa = await _validar_empresa_usuario(db, request.empresa_id, user_id)

        cert_bytes = certificado_service.descriptografar_certificado(
            empresa["certificado_a1"]
        )

        # SEGURANÇA: Senha vem do request (não do banco) para evitar exposição
        senha_cert = request.certificado_senha

        sefaz_response = sefaz_service.inutilizar_numeracao(
            empresa_cnpj=empresa["cnpj"],
            empresa_uf=empresa["uf"],
            serie=request.serie,
            numero_inicial=request.numero_inicio,
            numero_final=request.numero_fim,
            ano=datetime.now().year % 100,
            motivo=request.justificativa,
            cert_bytes=cert_bytes,
            senha_cert=senha_cert,
        )

        return sefaz_response

    except HTTPException:
        raise
    except EmissionBlockedError as e:
        logger.error(f"Emissão bloqueada por segurança: {e}")
        raise HTTPException(
            status_code=403,
            detail="Emissão bloqueada por configuração de segurança. " \
                   "Verifique as variáveis SEFAZ_AMBIENTE e ALLOW_PRODUCTION_EMISSION."
        )
    except SefazException as e:
        raise HTTPException(status_code=502, detail={"message": str(e)})
    except Exception as e:
        logger.error(f"Erro ao inutilizar: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
