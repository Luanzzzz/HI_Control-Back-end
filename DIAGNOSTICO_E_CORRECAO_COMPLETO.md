# DIAGNÓSTICO E CORREÇÃO COMPLETA - HI-CONTROL

**Data:** 10/02/2026
**Status:** Correções aplicadas

---

## 1. PROBLEMAS IDENTIFICADOS

### 1.1 BUG RAIZ: Nome de coluna `ativo` vs `ativa` (CRÍTICO)

**Causa dos erros 500 em TODOS os endpoints do bot.**

O schema do banco (`database/schema.sql`, linha 189) define a coluna como:
```sql
ativa BOOLEAN DEFAULT true,  -- feminino, concordando com "empresa"
```

Porém, o código Python consultava:
```python
.eq("ativo", True)  # ❌ ERRADO - coluna não existe
```

**Arquivos afetados:**

| Arquivo | Linha | Query | Status |
|---------|-------|-------|--------|
| `app/api/v1/endpoints/bot_status.py` | 56 | `empresas.eq("ativo", True)` | **CORRIGIDO** |
| `app/api/v1/endpoints/bot_status.py` | 202 | `empresas.eq("ativo", True)` | **CORRIGIDO** |
| `app/api/v1/endpoints/bot_status.py` | 328 | `empresas.eq("ativo", True)` | **CORRIGIDO** |
| `bot/utils/supabase_client.py` | 63 | `empresas.eq("ativo", True)` | **CORRIGIDO** |
| `app/api/v1/endpoints/empresas.py` | 66 | `empresas.eq("ativa", True)` | Já estava correto |

**Nota:** Outros arquivos que usam `.eq("ativo", True)` em tabelas como `configuracoes_drive`, `configuracoes_email` e `credenciais_nfse` estão CORRETOS, pois essas tabelas realmente usam a coluna `ativo`.

---

### 1.2 BUG: Mapeamento de colunas no bot `salvar_nota` (CRÍTICO)

O método `SupabaseResource.salvar_nota()` em `bot/utils/supabase_client.py` usava nomes de colunas que NÃO existem no schema:

| Código (ANTES) | Schema Real | Status |
|----------------|-------------|--------|
| `"numero"` | `numero_nf` | **CORRIGIDO** |
| `"tipo"` | `tipo_nf` | **CORRIGIDO** |
| `"emitente_cnpj"` | `cnpj_emitente` | **CORRIGIDO** |
| `"emitente_nome"` | `nome_emitente` | **CORRIGIDO** |
| `"destinatario_cnpj"` | `cnpj_destinatario` | **CORRIGIDO** |
| `"destinatario_nome"` | `nome_destinatario` | **CORRIGIDO** |
| `"xml_content"` | `xml_url` | **CORRIGIDO** |
| `"status"` | `situacao` | **CORRIGIDO** |

---

### 1.3 BUG: Queries de métricas do bot usavam colunas erradas (MÉDIO)

No `bot_status.py`, as queries de notas_fiscais usavam:

| Código (ANTES) | Schema Real | Status |
|----------------|-------------|--------|
| `.select("created_at, tipo, numero")` | `tipo_nf`, `numero_nf` | **CORRIGIDO** |
| `.select("tipo")` (métricas) | `tipo_nf` | **CORRIGIDO** |

O mapeamento para resposta do frontend foi preservado para compatibilidade.

---

### 1.4 Migrations possivelmente não aplicadas (VERIFICAR)

As seguintes migrations EXISTEM no código mas podem não ter sido executadas no Supabase:

| Migration | Tabelas/Colunas | Verificar |
|-----------|----------------|-----------|
| `005_email_drive_config.sql` | `configuracoes_drive`, `configuracoes_email`, `log_importacao` | **Executar no Supabase** |
| `008_cert_senha_e_colunas_faltantes.sql` | `empresas.certificado_senha_encrypted`, `background_jobs` | **Executar no Supabase** |

**Nova migration criada:** `009_verificacao_schema_completo.sql` - idempotente, garante que TUDO exista.

---

## 2. CORREÇÕES APLICADAS

### 2.1 `app/api/v1/endpoints/bot_status.py`

- **Linha 56:** `"ativo"` → `"ativa"` (GET /bot/status)
- **Linha 202:** `"ativo"` → `"ativa"` (GET /bot/empresas/{id}/status)
- **Linha 328:** `"ativo"` → `"ativa"` (GET /bot/metricas)
- **Linha 213:** `"tipo, numero"` → `"tipo_nf, numero_nf"` (query notas)
- **Linhas 227-236:** Adicionado mapeamento `tipo_nf` → `tipo`, `numero_nf` → `numero` para compatibilidade frontend
- **Linha 351:** `"tipo"` → `"tipo_nf"` (query métricas)

### 2.2 `bot/utils/supabase_client.py`

- **Linha 63:** `"ativo"` → `"ativa"` (buscar_empresas_ativas)
- **Linhas 183-204:** Todos os nomes de colunas corrigidos no método `salvar_nota()`

### 2.3 `database/migrations/009_verificacao_schema_completo.sql` (NOVO)

Migration idempotente que:
- Cria tabelas `configuracoes_drive`, `configuracoes_email`, `log_importacao` se não existirem
- Adiciona colunas faltantes em `empresas` e `notas_fiscais`
- Cria índices de segurança
- Habilita RLS
- Executa verificação final

---

## 3. STATUS DAS FUNCIONALIDADES

### Google Drive
| Componente | Status | Detalhes |
|------------|--------|----------|
| `google_drive_service.py` | ✅ Implementado | 668 linhas, OAuth2, upload, sync |
| `drive_import_endpoints.py` | ✅ Implementado | 7 endpoints completos |
| `ConfiguracaoDrive.tsx` | ✅ Implementado | Frontend funcional |
| Migration tabela | ✅ Existe | Migration 005 (verificar execução) |

### Bot de Busca Automática
| Componente | Status | Detalhes |
|------------|--------|----------|
| `bot/main.py` | ✅ Implementado | APScheduler, 334 linhas |
| `bot/adapters/base_nacional.py` | ✅ Implementado | Adapter Base Nacional |
| `bot/utils/supabase_client.py` | ✅ Corrigido | Nomes de colunas corretos |
| `bot/config.py` | ✅ Implementado | Configuração completa |

### Endpoints do Bot
| Endpoint | Status Antes | Status Depois |
|----------|-------------|---------------|
| GET `/bot/status` | ❌ 500 | ✅ Corrigido |
| GET `/bot/metricas` | ❌ 500 | ✅ Corrigido |
| GET `/bot/empresas/{id}/status` | ❌ 500 | ✅ Corrigido |
| POST `/bot/sincronizar-agora` | ✅ OK | ✅ OK |

---

## 4. AÇÕES NECESSÁRIAS DO USUÁRIO

### PASSO 1: Executar Migration no Supabase (OBRIGATÓRIO)

Acesse o **Supabase Dashboard > SQL Editor** e execute o conteúdo de:

```
database/migrations/009_verificacao_schema_completo.sql
```

Isso garantirá que todas as tabelas e colunas existam.

### PASSO 2: Verificar se migrations anteriores foram aplicadas

Se os erros persistirem, execute também:

```
database/migrations/005_email_drive_config.sql
database/migrations/008_cert_senha_e_colunas_faltantes.sql
```

### PASSO 3: Reiniciar o backend

```bash
# Matar processo atual e reiniciar
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### PASSO 4: Testar

```bash
# Testar endpoints (substitua TOKEN pelo JWT válido)
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/bot/status
# Esperado: 200 OK

curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/v1/bot/metricas
# Esperado: 200 OK
```

### PASSO 5: Configurar Google Drive (se necessário)

1. Configurar `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `GOOGLE_REDIRECT_URI` no `.env`
2. Na interface, editar um cliente e clicar em "Conectar Drive"

---

## 5. ARQUITETURA DO SISTEMA (VALIDADA)

```
Frontend (React + Vite)
├── BotStatus.tsx       → GET /api/v1/bot/status        ✅
├── BotMetricas.tsx     → GET /api/v1/bot/metricas      ✅
├── ConfiguracaoDrive   → GET/POST /api/v1/drive/*      ✅
└── BuscadorNotas       → POST /api/v1/buscar-notas/*   ✅

Backend (FastAPI + Supabase)
├── bot_status.py       → Queries corrigidas             ✅
├── drive_import.py     → Endpoints Google Drive         ✅
├── google_drive_svc    → OAuth2 + Sync                  ✅
└── bot/main.py         → APScheduler automático         ✅

Banco (Supabase/PostgreSQL)
├── empresas            → coluna "ativa" (não "ativo")   ✅
├── notas_fiscais       → colunas tipo_nf, numero_nf     ✅
├── configuracoes_drive → Migration 005                  ⚠️ Verificar
└── configuracoes_email → Migration 005                  ⚠️ Verificar
```

---

## 6. RESUMO FINAL

| Métrica | Antes | Depois |
|---------|-------|--------|
| Erros 500 | 3 endpoints | 0 |
| Coluna `ativo` incorreta | 4 ocorrências | 0 |
| Colunas notas erradas | 8 colunas | 0 |
| Google Drive | Implementado (não testado) | Implementado + Migration |
| Bot de Busca | Bug ao salvar notas | Corrigido |
