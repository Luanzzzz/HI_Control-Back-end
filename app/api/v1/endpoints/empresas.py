"""
Endpoints para gerenciamento de Empresas (Clientes)
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from typing import List, Optional
from supabase import Client
from app.dependencies import get_db, get_admin_db, get_current_user
from app.models.empresa import EmpresaCreate, EmpresaResponse
from datetime import datetime
import logging
import re

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[EmpresaResponse])
async def listar_empresas(
    skip: int = 0,
    limit: int = 100,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """Lista todas as empresas do usuário"""
    try:
        user_id = usuario["id"]
        logger.info(f"Listando empresas para usuário {user_id}")

        response = db.table("empresas")\
            .select("*")\
            .eq("usuario_id", usuario["id"])\
            .eq("ativa", True)\
            .range(skip, skip + limit - 1)\
            .execute()

        logger.info(f"Encontradas {len(response.data)} empresas para usuário {user_id}")
        return response.data

    except Exception as e:
        logger.error(f"Erro ao listar empresas: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao listar empresas. Tente novamente."
        )


@router.get("/check-cnpj/{cnpj}")
async def verificar_cnpj(
    cnpj: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """Verifica se empresa com CNPJ já existe para o usuário"""
    # Normalizar CNPJ para formato armazenado (XX.XXX.XXX/XXXX-XX)
    cnpj_digits = re.sub(r'\D', '', cnpj)
    if len(cnpj_digits) != 14:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CNPJ deve conter 14 dígitos"
        )

    cnpj_formatado = f"{cnpj_digits[:2]}.{cnpj_digits[2:5]}.{cnpj_digits[5:8]}/{cnpj_digits[8:12]}-{cnpj_digits[12:]}"

    try:
        response = db.table("empresas")\
            .select("id, razao_social, nome_fantasia, cnpj, ativa")\
            .eq("cnpj", cnpj_formatado)\
            .eq("usuario_id", usuario["id"])\
            .limit(1)\
            .execute()

        if response.data:
            empresa = response.data[0]
            return {
                "exists": True,
                "ativa": empresa.get("ativa", True),
                "empresa": {
                    "id": empresa["id"],
                    "razao_social": empresa["razao_social"],
                    "nome_fantasia": empresa.get("nome_fantasia"),
                }
            }

        return {"exists": False}

    except Exception as e:
        logger.error(f"Erro ao verificar CNPJ: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Erro ao verificar CNPJ"
        )


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED, include_in_schema=False)
async def criar_empresa(
    empresa: EmpresaCreate,
    response: Response,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    Cria nova empresa ou atualiza dados se CNPJ já existir para o usuário.

    Returns:
        - 201: Empresa criada com sucesso
        - 200: Empresa existente atualizada
        - 409: CNPJ já cadastrado (empresa inativa)
        - 422: Dados inválidos (CNPJ inválido, etc.)
    """
    try:
        empresa_dict = empresa.model_dump()
        empresa_dict["usuario_id"] = usuario["id"]
        cnpj = empresa_dict["cnpj"]  # Já formatado pelo validator

        logger.info(f"POST /empresas - CNPJ: {cnpj} - Usuário: {usuario['id']}")

        # Verificar se empresa com mesmo CNPJ já existe para este usuário
        existing = db.table("empresas")\
            .select("*")\
            .eq("cnpj", cnpj)\
            .eq("usuario_id", usuario["id"])\
            .limit(1)\
            .execute()

        if existing.data:
            empresa_existente = existing.data[0]

            # Se empresa está inativa (soft-deleted), retornar conflito
            if not empresa_existente.get("ativa", True):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "error": "CNPJ_INATIVO",
                        "message": f"Empresa com CNPJ {cnpj} foi removida anteriormente. Contate o suporte para reativar.",
                        "cnpj": cnpj
                    }
                )

            # Empresa ativa existe: atualizar dados
            logger.info(f"Atualizando empresa existente: {empresa_existente['id']} - CNPJ {cnpj}")

            update_data = {k: v for k, v in empresa_dict.items() if k not in ("usuario_id",)}
            update_data["updated_at"] = datetime.utcnow().isoformat()

            update_response = db.table("empresas")\
                .update(update_data)\
                .eq("id", empresa_existente["id"])\
                .execute()

            if not update_response.data:
                raise HTTPException(status_code=500, detail="Erro ao atualizar empresa")

            logger.info(f"Empresa atualizada com sucesso: {empresa_existente['id']}")

            response.status_code = status.HTTP_200_OK
            return {
                **update_response.data[0],
                "_action": "updated",
                "_message": "Dados da empresa atualizados com sucesso"
            }

        # Empresa não existe: criar nova
        logger.info(f"Criando nova empresa: CNPJ {cnpj}")

        now = datetime.utcnow().isoformat()
        empresa_dict["created_at"] = now
        empresa_dict["updated_at"] = now
        empresa_dict["ativa"] = True

        insert_response = db.table("empresas").insert(empresa_dict).execute()

        if not insert_response.data:
            raise HTTPException(status_code=500, detail="Erro ao criar empresa")

        logger.info(f"Empresa criada com sucesso: {insert_response.data[0].get('id')}")

        return {
            **insert_response.data[0],
            "_action": "created",
            "_message": "Empresa cadastrada com sucesso"
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e).lower()
        logger.error(f"Erro ao processar empresa: {type(e).__name__} - {str(e)}")

        # Detectar violação de unique constraint do PostgreSQL
        if "duplicate key" in error_msg or "unique" in error_msg or "23505" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "CNPJ_DUPLICADO",
                    "message": f"Empresa com CNPJ {empresa.cnpj} já está cadastrada",
                    "cnpj": empresa.cnpj,
                    "suggestion": "Verifique o CNPJ ou edite a empresa existente"
                }
            )

        raise HTTPException(
            status_code=500,
            detail="Erro interno ao processar empresa. Tente novamente."
        )

@router.get("/{empresa_id}", response_model=EmpresaResponse)
async def obter_empresa(
    empresa_id: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """Obtém detalhes de uma empresa"""
    response = db.table("empresas")\
        .select("*")\
        .eq("id", empresa_id)\
        .eq("usuario_id", usuario["id"])\
        .single()\
        .execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    return response.data

@router.put("/{empresa_id}", response_model=EmpresaResponse)
async def atualizar_empresa(
    empresa_id: str,
    empresa: EmpresaCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """Atualiza uma empresa existente"""
    # Verify ownership
    existing = db.table("empresas")\
        .select("id")\
        .eq("id", empresa_id)\
        .eq("usuario_id", usuario["id"])\
        .execute()
        
    if not existing.data:
         raise HTTPException(status_code=404, detail="Empresa não encontrada")

    empresa_dict = empresa.dict(exclude={"usuario_id"})
    empresa_dict["updated_at"] = datetime.now().isoformat()
    
    response = db.table("empresas")\
        .update(empresa_dict)\
        .eq("id", empresa_id)\
        .execute()
        
    return response.data[0]

@router.delete("/{empresa_id}")
async def deletar_empresa(
    empresa_id: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """Remove uma empresa (soft delete)"""
    # Verify ownership
    existing = db.table("empresas")\
        .select("id")\
        .eq("id", empresa_id)\
        .eq("usuario_id", usuario["id"])\
        .execute()

    if not existing.data:
         raise HTTPException(status_code=404, detail="Empresa não encontrada")

    # Soft delete
    response = db.table("empresas")\
        .update({"ativa": False, "deleted_at": datetime.now().isoformat()})\
        .eq("id", empresa_id)\
        .execute()

    return {"message": "Empresa removida com sucesso"}


@router.delete("/admin/cleanup-all")
async def limpar_todas_empresas(
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    """
    ADMIN: Remove PERMANENTEMENTE todas as empresas do usuário (inclusive inativas).
    ⚠️ Use apenas para testes/desenvolvimento. Não há como desfazer.
    """
    # Logging detalhado para debug
    logger.info(f"🧹 DELETE /admin/cleanup-all chamado - Usuário: {usuario.get('id')}")
    logger.info(f"📍 Request recebido com sucesso, iniciando limpeza...")

    try:
        # Buscar todas as empresas do usuário (ativas e inativas)
        todas = db.table("empresas")\
            .select("id, razao_social, cnpj, ativa")\
            .eq("usuario_id", usuario["id"])\
            .execute()

        if not todas.data:
            return {
                "message": "Nenhuma empresa encontrada para este usuário",
                "deleted_count": 0
            }

        count = len(todas.data)
        empresas_deletadas = [
            f"{e['razao_social']} ({e['cnpj']}) - {'ATIVA' if e['ativa'] else 'INATIVA'}"
            for e in todas.data
        ]

        logger.warning(
            f"LIMPEZA TOTAL - Usuário {usuario['id']} deletando {count} empresas: "
            f"{empresas_deletadas}"
        )

        # DELETE PERMANENTE (não é soft delete)
        response = db.table("empresas")\
            .delete()\
            .eq("usuario_id", usuario["id"])\
            .execute()

        logger.info(f"✅ Limpeza concluída: {count} empresas removidas permanentemente")

        return {
            "message": f"Limpeza concluída com sucesso",
            "deleted_count": count,
            "empresas_deletadas": empresas_deletadas
        }

    except Exception as e:
        logger.error(f"Erro ao limpar empresas: {type(e).__name__} - {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao limpar empresas: {str(e)}"
        )
