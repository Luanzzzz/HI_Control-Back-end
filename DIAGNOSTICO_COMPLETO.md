# DIAGNÓSTICO COMPLETO - BACKEND HI-CONTROL

## 1. ESTRUTURA DE DIRETÓRIOS
*(Parcialmente reconstruída)*
- `app/`
  - `main.py`
  - `api/`
    - `v1/`
      - `router.py`
      - `endpoints/`
        - `certificados.py`
        - `auth.py`
        - `empresas.py`
  - `models/`
    - `empresa.py`
- `requirements.txt`
- `vercel.json`

## 2. ARQUIVO PRINCIPAL
**Localização:** `app/main.py`
**Conteúdo (Resumo):**
```python
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import logging
from app.api.v1.router import api_router
from app.core.config import settings

app = FastAPI(..., redirect_slashes=False)

# CORS Middleware (Allow all Vercel domains)
app.add_middleware(CORSMiddleware, ...)

# ROUTER REGISTRATION
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
```

## 3. ROUTERS REGISTRADOS
**Arquivo:** `app/api/v1/router.py`
**Conteúdo Relevante:**
```python
# Auth
api_router.include_router(auth.router, prefix="/auth", tags=["Autenticação"])

# Certificados - NOTE O PREFIXO AQUI
api_router.include_router(certificados.router, prefix="/certificados", tags=["Certificados"])

# Empresas
api_router.include_router(empresas.router, prefix="/empresas", tags=["Empresas"])
```

## 4. ENDPOINT DE CERTIFICADOS
**Localização:** `app/api/v1/endpoints/certificados.py`
**Existe:** [X] SIM [ ] NÃO
**Conteúdo (Definição da Rota):**
```python
router = APIRouter(tags=["Certificados Digitais"])

@router.post(
    "/empresas/{empresa_id}/certificado",
    response_model=CertificadoUploadResponse,
    dependencies=[require_modules("emissor_notas")],
)
async def upload_certificado(...):
```
**Rota Resultante:** `/api/v1/certificados/empresas/{empresa_id}/certificado`

## 5. IMPORTS E DEPENDÊNCIAS
**Main.py Imports:**
- `from app.api.v1.router import api_router`
- `from app.core.config import settings`
- `from app.db.supabase_client import supabase_client`

**Certificados Imports:**
- `from fastapi import APIRouter`
- `from app.services.certificado_service import certificado_service`

## 6. INFORMAÇÕES DE DEPLOY
**Informação:** Repositório Git não detectado ou inacessível no ambiente atual.
**Último Deploy Confirmado:** (Suposição baseada em logs) Vercel, Python 3.12 Runtime.

## 7. CONFIGURAÇÃO VERCEL
**Arquivo:** `vercel.json`
```json
{
  "version": 2,
  "builds": [{"src": "app/main.py", "use": "@vercel/python"}],
  "rewrites": [{"source": "/api/v1/:path*", "destination": "app/main.py"}]
}
```

## 8. ROTAS ATIVAS
*(Simulação baseada em análise estática)*
- `POST /api/v1/certificados/empresas/{id}/certificado` (Rota Atual)
- `GET /api/v1/certificados/empresas/{id}/certificado/status` (Rota Atual)
- `POST /api/v1/auth/login`
- `GET /api/v1/empresas`

## 9. DEPENDÊNCIAS
**PyNFE Instalado:** [X] SIM (`pynfe>=0.5.0` no requirements.txt)
**Outros:** `fastapi`, `uvicorn`, `supabase`, `python-multipart`.

## 10. MODEL EMPRESA
**Arquivo:** `app/models/empresa.py`
**Campos (Pydantic):**
- `usuario_id`
- `razao_social`, `cnpj`
- `certificado_validade` (Date)
- **Nota:** Campos `certificado_a1` e `certificado_senha` NÃO estão no Pydantic (segurança), mas são usados no `db.table('empresas').update()` em `certificados.py`.

---

## RESUMO EXECUTIVO

**Arquivo Principal:** `app/main.py`
**Endpoint de Certificados Existe:** SIM
**Router de Certificados Registrado:** SIM
**PyNFE Instalado:** SIM
**Problema Crítico Detectado:** **Rota Incorreta (404 Loop)**.

**ANÁLISE DO PROBLEMA:**
O endpoint está definido como `/empresas/{id}/certificado` DENTRO do router de `certificados`.
Porém, o router `certificados` é registrado no main com o prefixo `/certificados`.
Isso gera a URL final:
👉 **`/api/v1/certificados/empresas/{id}/certificado`**

O Frontend provavelmente está chamando:
👉 **`/api/v1/empresas/{id}/certificado`**
Isso resulta em **404 Not Found**.

**PRÓXIMOS PASSOS:**
1. **Opção A (Recomendada):** Remover o prefixo `/certificados` no `app/api/v1/router.py` para o router de certificados, OU mover a definição do endpoint para o router de `empresas`.
2. **Opção B:** Ajustar a rota no `certificados.py` para apenas `/{empresa_id}/certificado` (mas manteria o `/certificados/` na URL).
3. **Opção C:** Ajustar a chamada no Frontend para incluir `/certificados`.

**Recomendação:** Ajustar o backend para alinhar com a semântica REST (`/empresas/{id}/certificado` deve pertencer ao recurso Empresa).
