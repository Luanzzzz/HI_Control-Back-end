"""
Endpoints para gerenciamento do Perfil da Contabilidade
"""
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from app.dependencies import get_db, get_current_user
from app.models.perfil import PerfilCreate, PerfilResponse
from datetime import datetime

router = APIRouter()

@router.get("/", response_model=PerfilResponse)
async def obter_perfil(
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Obtém o perfil da contabilidade do usuário logado"""
    response = db.table("perfil_contabilidade")\
        .select("*")\
        .eq("usuario_id", usuario["id"])\
        .execute() # .single() might fail if not exists, so handle list

    if not response.data:
        # If no profile exists, maybe return 404 or an empty structure?
        # Better to return 404 and let frontend prompt creation
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    return response.data[0]

@router.put("/", response_model=PerfilResponse)
async def atualizar_perfil(
    perfil: PerfilCreate,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_db)
):
    """Cria ou atualiza o perfil da contabilidade"""
    
    # Check if exists
    existing = db.table("perfil_contabilidade")\
        .select("*")\
        .eq("usuario_id", usuario["id"])\
        .execute()
    
    dados = perfil.dict(exclude_unset=True)
    dados["usuario_id"] = usuario["id"]
    dados["updated_at"] = datetime.now().isoformat()
    
    if existing.data:
        # Update
        response = db.table("perfil_contabilidade")\
            .update(dados)\
            .eq("usuario_id", usuario["id"])\
            .execute()
    else:
        # Create
        dados["created_at"] = datetime.now().isoformat()
        response = db.table("perfil_contabilidade")\
            .insert(dados)\
            .execute()
            
    if not response.data:
        raise HTTPException(status_code=500, detail="Erro ao salvar perfil")
        
    return response.data[0]
