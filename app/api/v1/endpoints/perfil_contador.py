"""
Endpoints para gestão do perfil da firma de contabilidade.

Funcionalidades:
- Obter/atualizar dados da firma (Razão Social, CNPJ, IE)
- Upload de logo da firma
- Upload de certificado digital A1 do contador
- Verificação de validade do certificado

Integração: Dados armazenados na tabela usuarios
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from supabase import Client
from datetime import date
from pydantic import BaseModel, Field, validator
from typing import Optional
import logging
import re

from app.dependencies import (
    get_admin_db,
    get_current_user,
)
from app.services.certificado_service import (
    certificado_service,
    CertificadoInvalidoError,
    CertificadoExpiradoError,
    SenhaIncorretaError,
    CertificadoError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/perfil-contador", tags=["Perfil da Contabilidade"])


# ============================================
# MODELOS PYDANTIC
# ============================================

class PerfilContadorUpdate(BaseModel):
    """Dados da firma de contabilidade para atualização"""
    razao_social: Optional[str] = Field(None, max_length=255)
    cnpj: Optional[str] = Field(None, max_length=18)
    inscricao_estadual: Optional[str] = Field(None, max_length=50)

    @validator('cnpj')
    def validar_cnpj(cls, v):
        """Valida formato do CNPJ"""
        if v is None:
            return v
        # Remove formatação
        cnpj_limpo = re.sub(r'\D', '', v)
        if len(cnpj_limpo) != 14:
            raise ValueError('CNPJ deve ter 14 dígitos')
        # Retorna formatado
        return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "razao_social": "Contabilidade Silva & Associados LTDA",
                    "cnpj": "12.345.678/0001-90",
                    "inscricao_estadual": "123.456.789.012"
                }
            ]
        }
    }


class LogoUploadRequest(BaseModel):
    """Request para upload de logo"""
    logo_base64: str = Field(
        ...,
        description="Logo em base64 (formato: data:image/png;base64,... ou apenas o base64)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "logo_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA..."
                }
            ]
        }
    }


class CertificadoUploadRequest(BaseModel):
    """Request para upload de certificado do contador"""
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


class PerfilContadorResponse(BaseModel):
    """Response com dados do perfil da firma"""
    razao_social: Optional[str]
    cnpj: Optional[str]
    inscricao_estadual: Optional[str]
    logo_url: Optional[str]
    certificado_validade: Optional[date]
    certificado_titular: Optional[str]
    certificado_emissor: Optional[str]


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
    validade: Optional[date]
    dias_restantes: Optional[int]
    status: str  # valido, expirando_em_breve, expirado, ausente
    requer_atencao: bool
    alerta: str
    titular: Optional[str]
    emissor: Optional[str]


# ============================================
# ENDPOINTS
# ============================================

@router.get(
    "",
    response_model=PerfilContadorResponse,
    summary="Obter perfil da contabilidade"
)
async def obter_perfil(
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Retorna dados da firma de contabilidade do usuário logado.

    **Campos retornados:**
    - `razao_social`: Razão Social da firma
    - `cnpj`: CNPJ formatado
    - `inscricao_estadual`: Inscrição Estadual
    - `logo_url`: URL ou base64 da logo
    - `certificado_validade`: Data de validade do certificado (se cadastrado)
    - `certificado_titular`: Titular do certificado
    - `certificado_emissor`: Emissor do certificado

    **Exemplo de resposta:**
    ```json
    {
      "razao_social": "Contabilidade Silva & Associados LTDA",
      "cnpj": "12.345.678/0001-90",
      "inscricao_estadual": "123.456.789.012",
      "logo_url": "https://...",
      "certificado_validade": "2027-01-26",
      "certificado_titular": "CONTABILIDADE SILVA:12345678000190",
      "certificado_emissor": "AC Certisign RFB G5"
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # Buscar dados do usuário
        response = db.table("usuarios") \
            .select(
                "razao_social_contador, cnpj_contador, inscricao_estadual_contador, "
                "logo_url_contador, certificado_contador_validade, "
                "certificado_contador_titular, certificado_contador_emissor"
            ) \
            .eq("id", user_id) \
            .single() \
            .execute()

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Usuário não encontrado"
            )

        data = response.data

        return PerfilContadorResponse(
            razao_social=data.get("razao_social_contador"),
            cnpj=data.get("cnpj_contador"),
            inscricao_estadual=data.get("inscricao_estadual_contador"),
            logo_url=data.get("logo_url_contador"),
            certificado_validade=data.get("certificado_contador_validade"),
            certificado_titular=data.get("certificado_contador_titular"),
            certificado_emissor=data.get("certificado_contador_emissor"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter perfil do contador: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )


@router.put(
    "",
    response_model=PerfilContadorResponse,
    summary="Atualizar perfil da contabilidade"
)
async def atualizar_perfil(
    perfil: PerfilContadorUpdate = Body(...),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Atualiza dados da firma de contabilidade.

    **Campos opcionais:**
    - `razao_social`: Razão Social da firma
    - `cnpj`: CNPJ (formato: 99.999.999/9999-99)
    - `inscricao_estadual`: Inscrição Estadual

    **Validações:**
    - CNPJ deve ter 14 dígitos (será formatado automaticamente)
    - Campos vazios não atualizam o registro

    **Exemplo de requisição:**
    ```json
    {
      "razao_social": "Contabilidade Silva & Associados LTDA",
      "cnpj": "12345678000190",
      "inscricao_estadual": "123.456.789.012"
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # Preparar dados para atualização (apenas campos não-None)
        update_data = {}
        if perfil.razao_social is not None:
            update_data["razao_social_contador"] = perfil.razao_social
        if perfil.cnpj is not None:
            update_data["cnpj_contador"] = perfil.cnpj
        if perfil.inscricao_estadual is not None:
            update_data["inscricao_estadual_contador"] = perfil.inscricao_estadual

        if not update_data:
            raise HTTPException(
                status_code=400,
                detail="Nenhum campo fornecido para atualização"
            )

        # Atualizar no banco
        response = db.table("usuarios") \
            .update(update_data) \
            .eq("id", user_id) \
            .execute()

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Usuário não encontrado"
            )

        logger.info(f"Perfil do contador atualizado: user_id={user_id}, campos={list(update_data.keys())}")

        # Retornar dados atualizados
        return await obter_perfil(usuario, db)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Erro ao atualizar perfil do contador: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )


@router.post(
    "/logo",
    summary="Upload de logo da contabilidade"
)
async def upload_logo(
    request: LogoUploadRequest = Body(...),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Upload de logo da firma de contabilidade.

    **Formato aceito:**
    - Base64 com ou sem prefixo `data:image/...;base64,`
    - Formatos de imagem: PNG, JPG, JPEG, SVG

    **Armazenamento:**
    - Logo armazenada como base64 no campo `logo_url_contador`
    - Tamanho recomendado: até 500KB

    **Exemplo de requisição:**
    ```json
    {
      "logo_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA..."
    }
    ```

    **Exemplo de resposta:**
    ```json
    {
      "mensagem": "Logo atualizada com sucesso",
      "logo_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA..."
    }
    ```
    """
    user_id = usuario["id"]

    try:
        logo_base64 = request.logo_base64

        # Verificar se já tem o prefixo data:image
        if not logo_base64.startswith('data:image'):
            # Adicionar prefixo genérico (assumir PNG)
            logo_base64 = f"data:image/png;base64,{logo_base64}"

        # Atualizar no banco
        response = db.table("usuarios") \
            .update({"logo_url_contador": logo_base64}) \
            .eq("id", user_id) \
            .execute()

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Usuário não encontrado"
            )

        logger.info(f"Logo do contador atualizada: user_id={user_id}")

        return {
            "mensagem": "Logo atualizada com sucesso",
            "logo_url": logo_base64
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao fazer upload de logo: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )


@router.post(
    "/certificado",
    response_model=CertificadoUploadResponse,
    summary="Upload de certificado digital do contador"
)
async def upload_certificado(
    request: CertificadoUploadRequest = Body(...),
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Upload de certificado digital A1 (.pfx/.p12) da firma de contabilidade.

    **Segurança:**
    - Certificado criptografado com Fernet antes de armazenar
    - Senha nunca é armazenada
    - Apenas o dono do perfil pode fazer upload

    **Validações:**
    - Arquivo deve ser .pfx/.p12 válido
    - Senha deve desbloquear o certificado
    - Certificado não pode estar expirado
    - Certificado deve conter chave privada

    **Processo:**
    1. Valida arquivo e senha
    2. Extrai informações (titular, emissor, validade)
    3. Criptografa certificado com Fernet
    4. Armazena no perfil do contador
    5. Retorna dados de validade

    **Alerta de expiração:**
    - `requer_atencao: true` se expirar em menos de 30 dias

    **Exemplo de requisição:**
    ```json
    {
      "certificado_base64": "MIIKlAIBAzCCCk4GCSqGSIb3DQEHA...",
      "senha": "certificadoSenha123"
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # Processar certificado
        logger.info(f"Processando upload de certificado do contador: user_id={user_id}")

        resultado = certificado_service.processar_upload(
            cert_base64_input=request.certificado_base64,
            senha=request.senha,
        )

        cert_criptografado = resultado["cert_criptografado"]
        info = resultado["info"]

        # Armazenar no perfil do contador
        db.table("usuarios").update({
            "certificado_contador_a1": cert_criptografado,
            "certificado_contador_validade": info["data_fim"].isoformat(),
            "certificado_contador_titular": info["titular"],
            "certificado_contador_emissor": info["emissor"],
        }).eq("id", user_id).execute()

        logger.info(
            f"Certificado do contador atualizado. "
            f"Válido até {info['data_fim']}, {info['dias_restantes']} dias restantes."
        )

        # Preparar resposta
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
        logger.error(f"Erro ao processar certificado: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar certificado: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Erro interno ao fazer upload de certificado: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )


@router.get(
    "/certificado/status",
    response_model=CertificadoStatusResponse,
    summary="Verificar status do certificado do contador"
)
async def verificar_status_certificado(
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db),
):
    """
    Verifica status de validade do certificado digital do contador.

    **Status possíveis:**
    - `valido`: Certificado válido (mais de 30 dias restantes)
    - `expirando_em_breve`: Expira em menos de 30 dias
    - `expirado`: Já expirou
    - `ausente`: Contador não possui certificado cadastrado

    **Uso recomendado:**
    - Chamar ao carregar dashboard
    - Chamar antes de tentar emitir NF-e
    - Implementar alerta visual quando `requer_atencao: true`

    **Exemplo de resposta (válido):**
    ```json
    {
      "validade": "2027-01-26",
      "dias_restantes": 365,
      "status": "valido",
      "requer_atencao": false,
      "alerta": "Certificado válido até 26/01/2027.",
      "titular": "CONTABILIDADE SILVA:12345678000190",
      "emissor": "AC Certisign RFB G5"
    }
    ```
    """
    user_id = usuario["id"]

    try:
        # Buscar dados do certificado
        response = db.table("usuarios") \
            .select(
                "certificado_contador_validade, certificado_contador_titular, "
                "certificado_contador_emissor"
            ) \
            .eq("id", user_id) \
            .single() \
            .execute()

        if not response.data:
            raise HTTPException(
                status_code=404,
                detail="Usuário não encontrado"
            )

        data = response.data

        # Verificar se tem certificado
        if not data.get("certificado_contador_validade"):
            return CertificadoStatusResponse(
                validade=None,
                dias_restantes=None,
                status="ausente",
                requer_atencao=True,
                alerta="Certificado digital não cadastrado. Faça o upload para emitir NF-e.",
                titular=None,
                emissor=None,
            )

        # Verificar expiração
        from datetime import datetime
        data_validade = datetime.fromisoformat(data["certificado_contador_validade"]).date()

        status_info = certificado_service.verificar_expiracao(data_validade)

        return CertificadoStatusResponse(
            validade=data_validade,
            dias_restantes=status_info["dias_restantes"],
            status=status_info["status"],
            requer_atencao=status_info["requer_atencao"],
            alerta=status_info["alerta"],
            titular=data.get("certificado_contador_titular"),
            emissor=data.get("certificado_contador_emissor"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao verificar status do certificado: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno: {str(e)}"
        )
