"""
Router agregador da API v1
"""
import os
from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, certificados, emissao_nfe, emissao_nfce, emissao_cte,
    emissao_nfse, empresas, perfil,
    perfil_contador, debug, nfse_endpoints, email_import_endpoints,
    drive_import_endpoints, suporte_emissao, bot_status, notas_drive,
    sync_endpoints, dashboard_endpoints,
)

# Criar router principal da v1
api_router = APIRouter()

# Auth
api_router.include_router(auth.router, prefix="/auth", tags=["Autenticacao"])

# Certificados
api_router.include_router(certificados.router, prefix="/certificados", tags=["Certificados"])

# NFe - Emissao
api_router.include_router(emissao_nfe.router, tags=["NFe - Emissao"])

# Empresas (Clientes)
api_router.include_router(empresas.router, prefix="/empresas", tags=["Empresas"])

# Dashboard agregado por empresa
api_router.include_router(dashboard_endpoints.router, tags=["Dashboard"])

# Perfil da Contabilidade
api_router.include_router(perfil.router, prefix="/perfil", tags=["Perfil"])

# Perfil do Contador (Dados da Firma + Certificado)
api_router.include_router(perfil_contador.router, tags=["Perfil Contador"])

# NFS-e - Notas Fiscais de Servico (APIs Municipais)
api_router.include_router(nfse_endpoints.router, tags=["NFS-e - Notas de Servico"])

# Email - Importacao via IMAP
api_router.include_router(email_import_endpoints.router, tags=["Email - Importacao"])

# Google Drive - Importacao de XMLs
api_router.include_router(drive_import_endpoints.router, tags=["Google Drive - Importacao"])

# Notas - Leitura direta do Drive
api_router.include_router(notas_drive.router, tags=["Notas - Drive"])

# NFC-e - Emissao (Modelo 65)
api_router.include_router(emissao_nfce.router, tags=["NFC-e - Consumidor"])

# Suporte a Emissao (Numeracao, CFOP, NCM, Produtos, Validacao)
api_router.include_router(suporte_emissao.router, tags=["Emissao - Suporte"])

# CT-e - Emissao (Modelo 57)
api_router.include_router(emissao_cte.router, tags=["CT-e - Transporte"])

# NFS-e - Emissao e Cancelamento
api_router.include_router(emissao_nfse.router, tags=["NFS-e - Emissao"])

# Bot - Status e Controle
api_router.include_router(bot_status.router, tags=["Bot Status"])

# Sync SEFAZ - controle de captura
api_router.include_router(sync_endpoints.router, tags=["Sync SEFAZ"])

# Debug: desabilitado por padrao.
# So habilita em ambiente nao-producao quando ENABLE_DEBUG_ROUTES=true.
env = os.getenv("ENVIRONMENT", "production").strip().lower()
enable_debug = os.getenv("ENABLE_DEBUG_ROUTES", "false").strip().lower() in {"1", "true", "yes", "on"}
if env != "production" and enable_debug:
    api_router.include_router(debug.router, prefix="/debug", tags=["Debug"])
