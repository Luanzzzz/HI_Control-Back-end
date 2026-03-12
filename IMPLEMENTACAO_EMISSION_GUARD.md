# ✅ IMPLEMENTAÇÃO DE PROTEÇÃO CONTRA EMISSÃO ACIDENTAL - CONCLUÍDA

**Data:** 2026-03-12
**Objetivo:** Impedir emissão acidental de NF-e/NFSe reais durante testes automatizados, CI/CD ou desenvolvimento

---

## 📋 RESUMO EXECUTIVO

### Status: ✅ **IMPLEMENTADO E TESTADO**

| Componente | Status | Arquivo |
|------------|--------|---------|
| **Emission Guard** | ✅ Implementado | `app/utils/emission_guard.py` |
| **Integração NFe** | ✅ Integrado | `app/services/sefaz_service.py` |
| **Integração NFSe** | ✅ Integrado | `app/services/nfse/emissao_nfse_service.py` |
| **Configuração** | ✅ Documentado | `.env.example` |
| **Testes unitários** | ✅ 16 testes criados | `tests/unit/test_emission_guard.py` |
| **Testes passando** | ✅ 16/16 (100%) | Todos os cenários cobertos |

---

## 🎯 PROBLEMA RESOLVIDO

### ANTES
- ❌ Testes automatizados podiam emitir NF-e real acidentalmente
- ❌ CI/CD poderia autorizar notas fiscais válidas na SEFAZ
- ❌ Erro humano em variáveis de ambiente causaria emissão em produção
- ❌ Cliente precisaria cancelar nota emitida por engano (problema fiscal)

### DEPOIS
- ✅ Proteção multicamadas contra emissão acidental
- ✅ Ambiente de testes NUNCA permite produção
- ✅ Produção requer flag explícita (double opt-in)
- ✅ Homologação sempre liberada (sem riscos)
- ✅ Log de auditoria de todas as emissões em produção

---

## 🔧 IMPLEMENTAÇÃO

### PASSO 1 — Diagnóstico (CONCLUÍDO)

**Variáveis de ambiente existentes:**
- `SEFAZ_AMBIENTE` — Já existia em `config.py` (homologacao/producao)
- `ALLOW_PRODUCTION_EMISSION` — Já existia em `config.py` (boolean)
- `ENVIRONMENT` — Já existia em `config.py` (development/test/production)

**Ponto de inserção identificado:**
- Arquivo NFe: `app/services/sefaz_service.py`
- Função: `autorizar_nfe()`
- Localização: **Linha 111** (PRIMEIRA linha do método, antes de qualquer processamento)

- Arquivo NFSe: `app/services/nfse/emissao_nfse_service.py`
- Função: `emitir_nfse()`
- Localização: Início do método

---

### PASSO 2 — Emission Guard (CONCLUÍDO)

**Arquivo:** [`app/utils/emission_guard.py`](d:\\Projetos\\Hi_Control\\backend\\app\\utils\\emission_guard.py)

**Classe de exceção:**
```python
class EmissionBlockedError(RuntimeError):
    """Erro levantado quando emissão em produção é bloqueada."""
    pass
```

**Função principal:**
```python
def verificar_permissao_emissao(
    empresa_id: str,
    tipo_documento: str = "NFe",
    raise_on_block: bool = True
) -> bool:
    """
    Verifica se emissão de documento fiscal em produção é permitida.

    Camadas de proteção:
    1. ENVIRONMENT=test NUNCA pode emitir em produção
    2. Produção requer ALLOW_PRODUCTION_EMISSION=true
    3. Homologação sempre permitida (sem riscos)

    Raises:
        EmissionBlockedError: Se emissão bloqueada e raise_on_block=True
    """
```

**Lógica de proteção (3 camadas):**

#### CAMADA 1: Homologação sempre liberada
```python
if sefaz_ambiente != "producao":
    logger.debug(f"✅ Emissão {tipo_documento} permitida - Ambiente: {sefaz_ambiente}")
    return True
```

#### CAMADA 2: Ambiente de testes NUNCA permite produção
```python
if environment == "test":
    raise EmissionBlockedError(
        "Tentativa de emitir em PRODUÇÃO durante execução de TESTES.\n"
        "Configure SEFAZ_AMBIENTE=homologacao para testes."
    )
```

#### CAMADA 3: Produção requer flag explícita
```python
if not allow_production:
    raise EmissionBlockedError(
        "Emissão em PRODUÇÃO bloqueada.\n"
        "Configure ALLOW_PRODUCTION_EMISSION=true no .env"
    )
```

#### CAMADA 4: Produção autorizada — LOG DE AUDITORIA
```python
logger.warning(
    "🟡 EMISSÃO EM PRODUÇÃO AUTORIZADA - "
    f"Empresa: {empresa_id} | Documento: {tipo_documento}"
)

# Registra em tabela de auditoria (se disponível)
_registrar_auditoria_emissao_producao(empresa_id, tipo_documento)
return True
```

---

### PASSO 3 — Integração nos Services (CONCLUÍDO)

#### NFe - `sefaz_service.py`

**Linha 111:**
```python
def autorizar_nfe(
    self,
    nfe_data: NotaFiscalCompletaCreate,
    ...
    empresa_id: Optional[str] = None,
):
    # ============================================
    # PROTEÇÃO: Verificar permissão de emissão
    # ============================================
    from app.utils.emission_guard import verificar_permissao_emissao
    verificar_permissao_emissao(
        empresa_id=empresa_id or empresa_cnpj,
        tipo_documento="NFe"
    )

    # ... resto do código de autorização
```

#### NFSe - `emissao_nfse_service.py`

```python
async def emitir_nfse(self, empresa_id: str, nfse_data: dict, ...):
    # PROTEÇÃO: Verificar permissão de emissão em produção
    from app.utils.emission_guard import verificar_permissao_emissao
    verificar_permissao_emissao(empresa_id=empresa_id, tipo_documento="NFSe")

    # ... resto do código de emissão
```

---

### PASSO 4 — Atualizar .env.example (CONCLUÍDO)

**Arquivo:** [`backend/.env.example`](d:\\Projetos\\Hi_Control\\backend\\.env.example)

**Documentação adicionada:**
```bash
# ============================================
# PROTEÇÃO CONTRA EMISSÃO ACIDENTAL EM PRODUÇÃO
# ============================================
# REGRAS DE SEGURANÇA (3 camadas de proteção):
#
# 1. Se SEFAZ_AMBIENTE=homologacao → Emissão sempre permitida (sem riscos)
# 2. Se SEFAZ_AMBIENTE=producao + ALLOW_PRODUCTION_EMISSION=false → BLOQUEADO
# 3. Se ENVIRONMENT=test → NUNCA permite emissão em produção (mesmo com flag=true)
#
# CONFIGURAÇÃO RECOMENDADA POR AMBIENTE:
#
# 📌 Desenvolvimento local:
#   SEFAZ_AMBIENTE=homologacao
#   ALLOW_PRODUCTION_EMISSION=false
#   ENVIRONMENT=development
#
# 📌 Testes automatizados / CI-CD:
#   SEFAZ_AMBIENTE=homologacao  ⬅️ CRÍTICO
#   ALLOW_PRODUCTION_EMISSION=false
#   ENVIRONMENT=test
#
# 📌 Produção (servidor):
#   SEFAZ_AMBIENTE=producao
#   ALLOW_PRODUCTION_EMISSION=true  ⬅️ Requer ação consciente
#   ENVIRONMENT=production
#
# ⚠️ ATENÇÃO:
# Uma nota fiscal emitida em produção requer cancelamento formal na SEFAZ.
# Esta flag existe para evitar emissões acidentais durante desenvolvimento/testes.

ALLOW_PRODUCTION_EMISSION=false
```

---

## 📊 CENÁRIOS DE PROTEÇÃO

### Tabela de Decisão

| SEFAZ_AMBIENTE | ALLOW_PRODUCTION_EMISSION | ENVIRONMENT | Resultado |
|----------------|---------------------------|-------------|-----------|
| homologacao    | false                     | development | ✅ **PERMITIDO** (homologação sem riscos) |
| homologacao    | true                      | development | ✅ **PERMITIDO** (homologação sem riscos) |
| producao       | false                     | production  | ❌ **BLOQUEADO** (flag=false) |
| producao       | true                      | production  | ✅ **PERMITIDO** (com auditoria) |
| producao       | false                     | test        | ❌ **BLOQUEADO** (ambiente test) |
| producao       | true                      | test        | ❌ **BLOQUEADO** (ambiente test) |

---

## 🧪 TESTES (CONCLUÍDO)

**Arquivo:** [`tests/unit/test_emission_guard.py`](d:\\Projetos\\Hi_Control\\backend\\tests\\unit\\test_emission_guard.py)

**Cobertura de testes:**

| # | Teste | Descrição | Status |
|---|-------|-----------|--------|
| 1 | `test_homologacao_sempre_permitida` | Homologação DEVE sempre permitir | ✅ PASSOU |
| 2 | `test_homologacao_com_raise_false` | Homologação com raise_on_block=False | ✅ PASSOU |
| 3 | `test_producao_bloqueada_levanta_excecao` | Produção com flag=false DEVE bloquear | ✅ PASSOU |
| 4 | `test_producao_bloqueada_retorna_false_com_raise_false` | Produção bloqueada retorna False | ✅ PASSOU |
| 5 | `test_producao_permitida_com_flag_true` | Produção com flag=true DEVE permitir | ✅ PASSOU |
| 6 | `test_ambiente_teste_nunca_permite_producao` | ENVIRONMENT=test NUNCA permite | ✅ PASSOU |
| 7-10 | `test_protecao_funciona_para_todos_documentos[NFe/NFSe/NFCe/CTe]` | Proteção para todos os tipos | ✅ PASSOU (4 testes parametrizados) |
| 11 | `test_ambiente_e_homologacao_helper` | Helper retorna True em homologação | ✅ PASSOU |
| 12 | `test_ambiente_e_homologacao_helper_producao` | Helper retorna False em produção | ✅ PASSOU |
| 13 | `test_forcar_ambiente_homologacao` | Helper força homologação | ✅ PASSOU |
| 14 | `test_resetar_cache_settings` | Helper limpa cache settings | ✅ PASSOU |
| 15 | `test_integracao_sefaz_service_homologacao` | SefazService permite em homologação | ✅ PASSOU |
| 16 | `test_integracao_sefaz_service_producao_bloqueado` | SefazService bloqueia produção | ✅ PASSOU |

**Resultado:**
```
16 passed, 1 warning in 2.03s
```

**Executar testes:**
```bash
pytest backend/tests/unit/test_emission_guard.py -v
```

---

## 📖 HELPERS DISPONÍVEIS

### Para uso em testes e fixtures:

```python
from app.utils.emission_guard import (
    ambiente_e_homologacao,
    forcar_ambiente_homologacao,
    resetar_cache_settings
)

# Verificar ambiente atual
if not ambiente_e_homologacao():
    pytest.skip("Teste apenas em homologação")

# Forçar homologação em setup de testes
forcar_ambiente_homologacao()

# Recarregar settings após mudar env vars
resetar_cache_settings()
```

---

## 🚀 EXEMPLOS DE USO

### Exemplo 1: Desenvolvimento local (seguro)

```bash
# .env
SEFAZ_AMBIENTE=homologacao
ALLOW_PRODUCTION_EMISSION=false
ENVIRONMENT=development
```

**Resultado:** ✅ Emissão permitida (homologação sem riscos)

---

### Exemplo 2: CI/CD GitHub Actions (seguro)

```yaml
# .github/workflows/test.yml
env:
  SEFAZ_AMBIENTE: homologacao  # CRÍTICO
  ALLOW_PRODUCTION_EMISSION: false
  ENVIRONMENT: test
```

**Resultado:** ✅ Emissão permitida (homologação)

Se alguém acidentalmente configurar:
```yaml
env:
  SEFAZ_AMBIENTE: producao  # ERRO!
  ENVIRONMENT: test
```

**Resultado:** ❌ **BLOQUEADO** (ENVIRONMENT=test nunca permite produção)

---

### Exemplo 3: Produção (requer ação consciente)

```bash
# .env (servidor de produção)
SEFAZ_AMBIENTE=producao
ALLOW_PRODUCTION_EMISSION=true  # ⬅️ Ação deliberada
ENVIRONMENT=production
```

**Resultado:** ✅ Emissão permitida (com log de auditoria)

**Log gerado:**
```
WARNING: 🟡 EMISSÃO EM PRODUÇÃO AUTORIZADA -
Empresa: uuid-empresa-123 |
Documento: NFe |
Ambiente: producao |
ALLOW_PRODUCTION_EMISSION: True
```

---

## 🔒 AUDITORIA DE EMISSÃO

Todas as emissões autorizadas em produção são registradas em:

1. **Log da aplicação** (nível WARNING)
2. **Tabela de auditoria** `audit_log` (se disponível)

**Estrutura do registro:**
```json
{
  "empresa_id": "uuid-empresa-123",
  "tipo_documento": "NFe",
  "ambiente": "producao",
  "timestamp": "2026-03-12T14:30:00",
  "action": "emission_production_allowed",
  "user_id": null
}
```

---

## ✅ CONCLUSÃO

### Status Final: **IMPLEMENTADO E PRONTO PARA USO**

**Benefícios alcançados:**
1. ✅ Proteção multicamadas contra emissão acidental
2. ✅ ENVIRONMENT=test nunca permite produção (proteção CI/CD)
3. ✅ Produção requer double opt-in (SEFAZ_AMBIENTE + flag)
4. ✅ Homologação sempre liberada (desenvolvimento fluido)
5. ✅ Auditoria automática de emissões em produção
6. ✅ Testes completos (16/16 passando)

**Gaps resolvidos:**
- ❌ Emissão acidental em testes → ✅ BLOQUEADO por ENVIRONMENT=test
- ❌ Emissão por erro em .env → ✅ BLOQUEADO por flag=false padrão
- ❌ Sem auditoria → ✅ LOG automático + tabela audit_log

**Próxima ação:**
- ✅ Commit da implementação
- ⏳ Validar em ambiente de testes/CI-CD
- ⏳ Documentar no README principal

---

**Última atualização:** 2026-03-12
**Responsável:** Claude Sonnet 4.5
**Commit:** Pendente
**Status:** ✅ IMPLEMENTAÇÃO COMPLETA
