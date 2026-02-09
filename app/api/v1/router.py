"""
Router agregador da API v1
"""
import os
from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, certificados, emissao_nfe, emissao_nfce, emissao_cte,
    emissao_nfse, buscar_notas, notas, empresas, perfil,
    perfil_contador, debug, nfse_endpoints, email_import_endpoints,
    drive_import_endpoints, suporte_emissao,
)

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

# NFS-e - Notas Fiscais de Serviço (APIs Municipais)
api_router.include_router(nfse_endpoints.router, tags=["NFS-e - Notas de Serviço"])

# Email - Importação via IMAP
api_router.include_router(email_import_endpoints.router, tags=["Email - Importação"])

# Google Drive - Importação de XMLs
api_router.include_router(drive_import_endpoints.router, tags=["Google Drive - Importação"])

# NFC-e - Emissão (Modelo 65)
api_router.include_router(emissao_nfce.router, tags=["NFC-e - Consumidor"])

# Suporte à Emissão (Numeração, CFOP, NCM, Produtos, Validação)
api_router.include_router(suporte_emissao.router, tags=["Emissão - Suporte"])

# CT-e - Emissão (Modelo 57)
api_router.include_router(emissao_cte.router, tags=["CT-e - Transporte"])

# NFS-e - Emissão e Cancelamento
api_router.include_router(emissao_nfse.router, tags=["NFS-e - Emissão"])

# Debug (apenas em desenvolvimento - ENVIRONMENT != "production")
if os.getenv("ENVIRONMENT", "development") != "production":
    api_router.include_router(debug.router, prefix="/debug", tags=["Debug 🔧"])
