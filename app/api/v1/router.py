"""
Router agregador da API v1
"""
import os
from fastapi import APIRouter
from app.api.v1.endpoints import auth, certificados, emissao_nfe, buscar_notas, notas, empresas, perfil, perfil_contador, debug

# Criar router principal da v1
api_router = APIRouter()

# Auth
api_router.include_router(auth.router, prefix="/auth", tags=["Autenticação"])

# Certificados
api_router.include_router(certificados.router, prefix="/certificados", tags=["Certificados"])

# NFe - Emissão
api_router.include_router(emissao_nfe.router, tags=["NFe - Emissão"])

# NFe - Busca (DistribuicaoDFe)
api_router.include_router(buscar_notas.router, tags=["NFe - Busca"])

# Notas - Gestão (DB Local)
api_router.include_router(notas.router, prefix="/notas", tags=["Notas - Gestão"])

# Empresas (Clientes)
api_router.include_router(empresas.router, prefix="/empresas", tags=["Empresas"])

# Perfil da Contabilidade
api_router.include_router(perfil.router, prefix="/perfil", tags=["Perfil"])

# Perfil do Contador (Dados da Firma + Certificado)
api_router.include_router(perfil_contador.router, tags=["Perfil Contador"])

# Debug (apenas em desenvolvimento)
if os.getenv("ENVIRONMENT") == "development":
    api_router.include_router(debug.router, prefix="/debug", tags=["Debug 🔧"])
