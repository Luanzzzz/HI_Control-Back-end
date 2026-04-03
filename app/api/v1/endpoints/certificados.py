"""
Endpoints para gestão de certificados digitais A1.

Funcionalidades:
- Upload de certificado .pfx/.p12
- Verificação de validade
- Status de expiração
- Segurança: Fernet encryption

Requer módulo: emissor_notas
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Path
from supabase import Client
from datetime import date
from pydantic import BaseModel, Field
import logging

from app.dependencies import (
    get_admin_db,
    get_current_user,
    require_modules,
)
from app.services.certificado_service import (
    certificado_service,
    CertificadoInvalidoError,
    CertificadoExpiradoError,
    SenhaIncorretaError,
    CertificadoError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Certificados Digitais"])


# ============================================
# MODELOS PYDANTIC
# ============================================

class CertificadoUploadRequest(BaseModel):
    """Request para upload de certificado"""
    certificado_base64: str = Field(
        ...,
        description="Arquivo .pfx/.p12 codificado em base64"
    )
    senha: str = Field(
        ...,
        min_length=1,
        description="Senha do certificado digital"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "certificado_base64": "MIIKlAIBAzCCCk4GCSqGSIb3DQEHAa...",
                    "senha": "senhaSegura123"
                }
            ]
        }
    }


class CertificadoUploadResponse(BaseModel):
    """Response do upload de certificado"""
    mensagem: str
    validade: date
    dias_restantes: int
    titular: str
    emissor: str
    requer_atencao: bool


class CertificadoStatusResponse(BaseModel):
    """Status de validade do certificado"""
    validade: date | None
    dias_restantes: int | None
    status: str  # valido, expirando_em_breve, expirado, ausente
    requer_atencao: bool
    alerta: str
    titular: str | None = None
    emissor: str | None = None


# ============================================
# UPLOAD DE CERTIFICADO
# ============================================

@router.post(
    "/empresas/{empresa_id}/certificado",
    response_model=CertificadoUploadResponse,
    dependencies=[require_modules("emissor_notas")],
)
async def upload_certificado(
    empresa_id: str = Path(..., description="ID da empresa"),
    request: CertificadoUploadRequest = Body(...),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Upload de certificado digital A1 (.pfx/.p12).

    **Requer módulo**: `emissor_notas`

    **Segurança** (CRÍTICO):
    - Certificado criptografado com Fernet antes de armazenar
    - **IMPORTANTE**: Senha NÃO é armazenada no banco de dados
    - Senha deve ser fornecida pelo usuário a cada operação de emissão
    - Endpoints de emissão (POST /nfe/autorizar, POST /nfce/autorizar, POST /cte/autorizar)
      exigem campo `certificado_senha` no request
    - Apenas o dono da empresa pode fazer upload

    **Validações**:
    - Arquivo deve ser .pfx/.p12 válido
    - Senha deve desbloquear o certificado
    - Certificado não pode estar expirado
    - Certificado deve conter chave privada

    **Processo**:
    1. Valida arquivo e senha
    2. Extrai informações (titular, emissor, validade)
    3. Criptografa certificado com Fernet
    4. Armazena na empresa
    5. Retorna dados de validade

    **Alerta de expiração**:
    - `requer_atencao: true` se expirar em menos de 30 dias

    **Exemplo de requisição**:
    ```json
    {
      "certificado_base64": "MIIKlAIBAzCCCk4GCSqGSIb3DQEHA...",
      "senha": "certificadoSenha123"
    }
    ```

    **Exemplo de resposta (sucesso)**:
    ```json
    {
      "mensagem": "Certificado digital atualizado com sucesso",
      "validade": "2027-01-26",
      "dias_restantes": 365,
      "titular": "EMPRESA TESTE LTDA:12345678000190",
      "emissor": "AC Certisign RFB G5",
      "requer_atencao": false
    }
    ```

    **Exemplo de resposta (expirando em breve)**:
    ```json
    {
      "mensagem": "Certificado digital atualizado. ATENÇÃO: Expira em 15 dias!",
      "validade": "2026-02-10",
      "dias_restantes": 15,
      "titular": "EMPRESA TESTE LTDA:12345678000190",
      "emissor": "AC Certisign RFB G5",
      "requer_atencao": true
    }
    ```

    **Erros possíveis**:
    - `400`: Certificado inválido, senha incorreta, ou expirado
    - `404`: Empresa não encontrada
    - `403`: Usuário não é dono da empresa
    """
    user_id = usuario["id"]

    try:
        # 1. Validar empresa pertence ao usuário
        empresa = await _validar_empresa_usuario(db, empresa_id, user_id)

        # 2. Processar certificado
        logger.info(f"Processando upload de certificado para empresa {empresa['cnpj']}")

        resultado = certificado_service.processar_upload(
            cert_base64_input=request.certificado_base64,
            senha=request.senha,
        )

        cert_criptografado = resultado["cert_criptografado"]
        info = resultado["info"]

        # 3. Armazenar na empresa (SEGURANÇA: senha NÃO é persistida no banco)
        # SEGURANÇA: Senha do certificado não é persistida no banco.
        # A senha deve ser fornecida pelo usuário a cada operação de emissão.
        # Salvamos apenas o certificado (criptografado) e seus metadados.
        db.table("empresas").update({
            "certificado_a1": cert_criptografado,
            "certificado_validade": info["data_fim"].isoformat(),
            "certificado_titular": info["titular"],
            "certificado_emissor": info["emissor"],
        }).eq("id", empresa_id).execute()

        logger.info(
            f"Certificado atualizado para empresa {empresa['cnpj']}. "
            f"Válido até {info['data_fim']}, {info['dias_restantes']} dias restantes."
        )

        # 4. Preparar resposta
        mensagem = "Certificado digital atualizado com sucesso"
        if info["requer_atencao"]:
            mensagem += f". ATENÇÃO: Expira em {info['dias_restantes']} dias!"

        return CertificadoUploadResponse(
            mensagem=mensagem,
            validade=info["data_fim"],
            dias_restantes=info["dias_restantes"],
            titular=info["titular"],
            emissor=info["emissor"],
            requer_atencao=info["requer_atencao"],
        )

    except HTTPException:
        raise
    except SenhaIncorretaError:
        raise HTTPException(
            status_code=400,
            detail="Senha do certificado incorreta. Verifique e tente novamente."
        )
    except CertificadoExpiradoError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except CertificadoInvalidoError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Certificado inválido: {str(e)}"
        )
    except CertificadoError as e:
        logger.error(f"Erro ao processar certificado", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao processar certificado. Contate o suporte."
        )
    except Exception as e:
        logger.error(f"Erro interno ao fazer upload de certificado", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao processar certificado. Contate o suporte."
        )


# ============================================
# CONSULTA DE STATUS DO CERTIFICADO
# ============================================

@router.get(
    "/empresas/{empresa_id}/certificado/status",
    response_model=CertificadoStatusResponse,
    dependencies=[require_modules("emissor_notas")],
)
async def verificar_status_certificado(
    empresa_id: str = Path(..., description="ID da empresa"),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Verifica status de validade do certificado digital.

    **Requer módulo**: `emissor_notas`

    **Status possíveis**:
    - `valido`: Certificado válido (mais de 30 dias restantes)
    - `expirando_em_breve`: Expira em menos de 30 dias
    - `expirado`: Já expirou
    - `ausente`: Empresa não possui certificado cadastrado

    **Uso recomendado**:
    - Chamar ao carregar dashboard
    - Chamar antes de tentar emitir NF-e
    - Implementar alerta visual quando `requer_atencao: true`

    **Exemplo de resposta (válido)**:
    ```json
    {
      "validade": "2027-01-26",
      "dias_restantes": 365,
      "status": "valido",
      "requer_atencao": false,
      "alerta": "Certificado válido até 26/01/2027.",
      "titular": "EMPRESA TESTE LTDA:12345678000190",
      "emissor": "AC Certisign RFB G5"
    }
    ```

    **Exemplo de resposta (expirando em breve)**:
    ```json
    {
      "validade": "2026-02-10",
      "dias_restantes": 15,
      "status": "expirando_em_breve",
      "requer_atencao": true,
      "alerta": "Certificado digital expira em 15 dias. Renove com antecedência.",
      "titular": "EMPRESA TESTE LTDA:12345678000190",
      "emissor": "AC Certisign RFB G5"
    }
    ```

    **Exemplo de resposta (expirado)**:
    ```json
    {
      "validade": "2025-12-01",
      "dias_restantes": -56,
      "status": "expirado",
      "requer_atencao": true,
      "alerta": "Certificado digital expirou há 56 dias. Renove imediatamente.",
      "titular": "EMPRESA TESTE LTDA:12345678000190",
      "emissor": "AC Certisign RFB G5"
    }
    ```

    **Exemplo de resposta (ausente)**:
    ```json
    {
      "validade": null,
      "dias_restantes": null,
      "status": "ausente",
      "requer_atencao": true,
      "alerta": "Certificado digital não cadastrado. Faça o upload para emitir NF-e.",
      "titular": null,
      "emissor": null
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # 1. Validar empresa
        empresa = await _validar_empresa_usuario(db, empresa_id, user_id)

        # 2. Verificar se tem certificado
        if not empresa.get("certificado_a1") or not empresa.get("certificado_validade"):
            return CertificadoStatusResponse(
                validade=None,
                dias_restantes=None,
                status="ausente",
                requer_atencao=True,
                alerta="Certificado digital não cadastrado. Faça o upload para emitir NF-e.",
                titular=None,
                emissor=None,
            )

        # 3. Verificar expiração
        from datetime import datetime
        data_validade = datetime.fromisoformat(empresa["certificado_validade"]).date()

        status_info = certificado_service.verificar_expiracao(data_validade)

        # 4. Retornar informações do certificado armazenadas no banco
        return CertificadoStatusResponse(
            validade=data_validade,
            dias_restantes=status_info["dias_restantes"],
            status=status_info["status"],
            requer_atencao=status_info["requer_atencao"],
            alerta=status_info["alerta"],
            titular=empresa.get("certificado_titular"),
            emissor=empresa.get("certificado_emissor"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao verificar status do certificado", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao verificar status do certificado. Contate o suporte."
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
                detail="Empresa não encontrada ou você não tem permissão para acessá-la"
            )

        # Retornar primeiro (e único) resultado
        return response.data[0]

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log e lançar erro genérico para outros erros
        logger.error(f"Erro ao validar empresa {empresa_id}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro ao validar empresa. Contate o suporte."
        )
