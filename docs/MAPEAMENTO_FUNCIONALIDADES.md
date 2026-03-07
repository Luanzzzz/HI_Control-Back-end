# Mapeamento de Funcionalidades - HI-Control Back-end

Data da revisao: 2026-03-07

## 1. Arquitetura geral

- API REST em FastAPI (`app/main.py`, `app/api/v1/router.py`)
- Persistencia via Supabase/PostgreSQL (`app/db/supabase_client.py` + migrations SQL)
- Processamento fiscal em services (`app/services/*`)
- Jobs recorrentes:
  - scheduler geral (`app/services/scheduler_service.py`)
  - worker de captura (`app/worker/sync_worker.py`)

## 2. Modulos de negocio

### 2.1 Autenticacao e perfil

- Login/logout/me (`app/api/v1/endpoints/auth.py`)
- Perfil do usuario e dados do contador (`perfil.py`, `perfil_contador.py`)
- Controle de plano e permissoes por endpoints/dependencies

### 2.2 Empresas (clientes do contador)

- CRUD completo de empresas (`app/api/v1/endpoints/empresas.py`)
- Preview de certificado no cadastro
- Reprocessamento de municipio e validacoes de consistencia

### 2.3 Certificado digital A1

- Upload e renovacao (`app/api/v1/endpoints/certificados.py`)
- Armazenamento criptografado do certificado e senha
- Carregamento/uso centralizado em `app/services/certificado_service.py`

### 2.4 Captura e sincronizacao de notas

#### Sync SEFAZ/NFS-e

- Endpoints de status/forcar/historico/configuracao:
  - `app/api/v1/endpoints/sync_endpoints.py`
- Service principal:
  - `app/services/captura_sefaz_service.py`
- Worker:
  - `app/worker/sync_worker.py`

Fluxos implementados:
- priorizacao por notas recentes (modo de primeira carga)
- controle de progresso em `sync_empresas` (percentual, etapa, estimativa)
- tipos habilitados por configuracao (NFSE/NFE/NFCE/CTE)
- tratamento de erros com backoff e registro em `sync_log`

### 2.5 NFS-e (Sistema Nacional e adaptadores)

- Service orquestrador: `app/services/nfse/nfse_service.py`
- Adaptadores:
  - `app/services/nfse/sistema_nacional.py`
  - `app/services/nfse/adapters/*` (municipais e variacoes)
- Fallback configuravel para cenarios sem integracao municipal

### 2.6 Dashboard e buscador de notas

- Endpoints agregados:
  - `app/api/v1/endpoints/dashboard_endpoints.py`
- Entregas principais:
  - resumo financeiro mensal
  - historico de movimentacao (12 meses)
  - listagem paginada de notas com filtros (tipo/status/retencao/busca/datas)
  - download de XML por nota
  - visualizacao/download de PDF (oficial quando disponivel)
  - link de consulta no portal oficial

### 2.7 Importacao/exportacao Google Drive

- Endpoints:
  - `app/api/v1/endpoints/drive_import_endpoints.py`
- Service:
  - `app/services/google_drive_service.py`

Capacidades atuais:
- OAuth do Google Drive
- sincronizacao de estrutura de pastas por cliente
- importacao de XML do Drive
- exportacao em massa de XML com job assíncrono e progresso

### 2.8 Emissao fiscal

- NFe: `emissao_nfe.py`
- NFCe: `emissao_nfce.py`
- CTe: `emissao_cte.py`
- NFSe: `emissao_nfse.py`
- Suporte emissao (CFOP/NCM/produtos/validacoes): `suporte_emissao.py`

## 3. Persistencia e migrations relevantes

Migrations mais sensiveis ao buscador/sync:
- `011_bot_captura.sql`
- `012_auto_credenciais_nfse_certificado.sql`
- `013_sync_progress_tracking.sql`
- `014_admin_plano_e_config_sync.sql`

Entidades-chave:
- `notas_fiscais`
- `sync_empresas`
- `sync_log`
- `sync_configuracoes_contador`
- `sync_configuracoes_empresa`
- tabelas de Google Drive export/import jobs

## 4. Seguranca

- JWT para autenticacao de API
- criptografia de certificado/senha (Fernet)
- RLS/validador de empresa por usuario autenticado nos endpoints de dados fiscais
- controles de CORS centralizados no `main.py`

## 5. Observabilidade e operacao

- logs estruturados de rotas no startup
- logs de request/response (sem OPTIONS)
- status do bot e metricas em endpoints dedicados (`bot_status.py`, `sync_endpoints.py`)

## 6. Testabilidade

- `pytest.ini` define suite padrao unit/regressao e separa integracao por marker
- cobertura de regressao para:
  - filtros e normalizacoes do dashboard
  - download XML/PDF por nota
  - fluxos de exportacao/importacao Drive
  - parser de tipos fiscais e filtros de captura
  - selecao de adapters NFS-e
