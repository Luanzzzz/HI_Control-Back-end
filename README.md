# HI-Control Back-end

API FastAPI para gestao contabil/fiscal com foco em captura de notas, emissao fiscal e automacoes para escritorio contabil.

## Visao geral

Este backend centraliza:

- autenticacao e controle de plano
- cadastro de empresas/clientes do contador
- captura automatica de notas fiscais (SEFAZ + NFS-e)
- dashboard financeiro por empresa
- download de XML/PDF por nota
- importacao/exportacao de XML por Email e Google Drive
- emissao fiscal (NFe, NFCe, CTe, NFSe)
- worker de sincronizacao periodica

## Stack atual

- Python 3.12
- FastAPI
- Supabase (PostgreSQL via REST)
- APScheduler (jobs recorrentes)
- PyNFE (quando disponivel no runtime)
- lxml / signxml / cryptography

## Estrutura principal

```text
app/
  api/v1/endpoints/      # rotas da API
  services/              # regras de negocio
  services/nfse/         # adapters NFS-e (nacional + municipais)
  worker/                # worker de sincronizacao SEFAZ
  core/                  # config e seguranca
  db/                    # cliente Supabase e repositorios
database/
  migrations/            # migrations SQL (001..015)
tests/
  unitarios e integracao
```

## Modulos funcionais mapeados

### 1) Autenticacao e perfil

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET/PUT /api/v1/perfil/`
- endpoints de perfil do contador em `perfil_contador.py`

### 2) Empresas (clientes do contador)

- CRUD de empresas em `app/api/v1/endpoints/empresas.py`
- preview de certificado antes de salvar empresa
- reprocessamento de municipio da empresa

### 3) Certificados A1

- upload, consulta e renovacao em `certificados.py`
- senha de certificado criptografada
- suporte a fallback de decrypt legado para compatibilidade

### 4) Buscador de notas e dashboard

Endpoints em `dashboard_endpoints.py`:

- `GET /api/v1/empresas/{empresa_id}/dashboard`
- `GET /api/v1/empresas/{empresa_id}/notas`
- `GET /api/v1/empresas/{empresa_id}/notas/{nota_id}`
- `GET /api/v1/empresas/{empresa_id}/notas/{nota_id}/xml`
- `GET /api/v1/empresas/{empresa_id}/notas/{nota_id}/pdf`
- `GET /api/v1/empresas/{empresa_id}/notas/{nota_id}/portal-oficial`

Funcionalidades:

- filtros por tipo/status/retencao/busca/data
- paginacao
- resumo financeiro mensal e historico 12 meses
- tentativa de PDF oficial (portal fiscal) com fallback controlado

### 5) Captura automatica de notas

#### SEFAZ Sync

`sync_endpoints.py`:

- status de sync por empresa
- forcar sincronizacao (somente plano admin)
- historico de sincronizacao
- configuracao global e configuracao por empresa

`captura_sefaz_service.py`:

- distribuicao DFe
- parse de modelos (55, 65, 57 e correlatos)
- controle de cursor NSU
- atualizacao de progresso de captura

#### NFS-e

`nfse_service.py` + adapters em `app/services/nfse/`:

- suporte ao Sistema Nacional
- adapters municipais (BH, SP, RJ, Curitiba, Porto Alegre, Fortaleza, Manaus)
- auto-credencial por certificado quando aplicavel

### 6) Google Drive (importacao + exportacao em massa)

`drive_import_endpoints.py` + `google_drive_service.py`:

- OAuth
- sincronizacao de pastas por cliente
- importacao de XML
- exportacao em massa de XML para Drive (jobs com progresso)

### 7) Emissao fiscal

- NFe: `emissao_nfe.py`
- NFCe: `emissao_nfce.py`
- CTe: `emissao_cte.py`
- NFSe: `emissao_nfse.py`
- suporte de emissao (CFOP/NCM/produtos/validacoes): `suporte_emissao.py`

## Rotas e docs

Com a API local em execucao:

- Swagger: `http://localhost:8000/api/v1/docs`
- ReDoc: `http://localhost:8000/api/v1/redoc`
- OpenAPI JSON: `http://localhost:8000/api/v1/openapi.json`

## Variaveis de ambiente (essenciais)

Exemplos no `.env.example`.

Campos criticos:

- `SECRET_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`
- `CERTIFICATE_ENCRYPTION_KEY`
- `SEFAZ_AMBIENTE` (`producao` ou `homologacao`)

Google Drive:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`

## Execucao local

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Worker e scheduler

No startup (fora de ambiente serverless):

- inicia scheduler de tarefas
- inicia worker de sincronizacao SEFAZ

Em ambiente serverless (ex. Vercel), o backend pula worker/scheduler no lifespan.

## Testes

### Suite padrao (unitaria/regressao)

```bash
pytest -q
```

Configuracao em `pytest.ini`:

- executa apenas `tests/`
- ignora `@pytest.mark.integration` por padrao

### Suite de integracao (opt-in)

```bash
pytest -m integration -v
```

Use para cenarios que dependem de servicos externos (SEFAZ, PyNFE real, etc.).

## Observacoes de qualidade

- o projeto possui arquivos legados de diagnostico na raiz; eles nao fazem parte da suite padrao de testes
- para manter a coleta de testes estavel, use sempre `pytest` com `pytest.ini` versionado
- para features com dependencia externa, mantenha testes unitarios com mocks + integracao opt-in

## Documentacao complementar

- `docs/MAPEAMENTO_FUNCIONALIDADES.md`
- `docs/RELATORIO_REVISAO_TESTES_2026-03-07.md`

