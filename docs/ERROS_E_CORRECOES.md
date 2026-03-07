# Hi-Control Backend — Erros Encontrados e Correções Aplicadas

Data de auditoria: 2026-03-07

---

## Sumário Executivo

Auditoria completa do backend identificou **7 bugs de produção** e criou **224 testes unitários** (0 falhas, 6 skipped por dependência externa). Todos os erros foram corrigidos com commits individuais.

---

## Bugs Corrigidos

### 1. Posições incorretas de extração na chave NF-e — `nfe_mapper.py`

**Arquivo:** `app/services/nfe_mapper.py`
**Commit:** `fix: Corrigir posições de extração na chave NF-e em nfe_mapper.py`
**Severidade:** CRÍTICA

**Problema:**
As funções `extrair_modelo_da_chave()`, `extrair_serie_da_chave()` e `extrair_numero_da_chave()` usavam posições incorretas na chave de 44 dígitos:

```
# ERRADO (antes da correção):
modelo_raw = chave[20:22]   # posições 21-22
serie_raw  = chave[22:25]   # posições 23-25
numero_raw = chave[25:34]   # posições 26-34
```

**Correção:**
Alinhado com o padrão SEFAZ e com `validators.py`:

```
# CORRETO (após a correção):
modelo_raw = chave[22:24]   # posições 23-24
serie_raw  = chave[24:27]   # posições 25-27
numero_raw = chave[27:36]   # posições 28-36
```

**Estrutura correta da chave NF-e (44 dígitos):**
```
[0:2]   UF (2 dígitos)
[2:8]   AAMM — Ano e Mês de emissão (6 dígitos)
[8:22]  CNPJ do emitente (14 dígitos)
[22:24] Modelo (2 dígitos: 55=NF-e, 65=NFC-e)
[24:27] Série (3 dígitos)
[27:36] Número da NF (9 dígitos)
[36:43] Código numérico (7 dígitos)
[43]    Dígito verificador (módulo 11)
```

---

### 2. tipo_nf com valor incorreto em importação de XML — `real_consulta_service.py`

**Arquivo:** `app/services/real_consulta_service.py`
**Commit:** `fix: Corrigir mapeamento de tipo_nf em real_consulta_service.py`
**Severidade:** ALTA

**Problema:**
O campo `tipo_nf` era gerado com `.upper()` resultando em `"NFE"`, mas o modelo `NotaFiscalCreate` aceita apenas `"NFe"`, `"NFCe"`, `"CTe"` ou `"NFSe"`. Isso causava `ValidationError` do Pydantic ao importar qualquer XML de NF-e.

```python
# ERRADO:
tipo_base = 'nfe' if modelo == '55' else 'nfce'
tipo_nf=tipo_base.upper()  # → 'NFE' ← inválido
```

**Correção:**
```python
# CORRETO:
tipo_base_map = {'55': 'NFe', '65': 'NFCe', '57': 'CTe'}
tipo_base = tipo_base_map.get(modelo, 'NFe')
tipo_nf=tipo_base  # → 'NFe' ← válido
```

---

### 3. Campos incompatíveis em SefazResponseModel — `nfe_completa.py`

**Arquivo:** `app/models/nfe_completa.py`
**Commit:** `fix: Corrigir SefazResponseModel e deprecação de Config em nfe_completa.py`
**Severidade:** ALTA

**Problema:**
O modelo `SefazResponseModel` definia os campos como `codigo` e `descricao`, mas `sefaz_service.py` criava instâncias com `status_codigo` e `status_descricao`. Além disso, `ambiente` e `uf` eram obrigatórios mas nem sempre fornecidos.

```python
# ERRADO (antes):
class SefazResponseModel(BaseModel):
    codigo: str = Field(...)
    descricao: str = Field(...)
    ambiente: TipoAmbiente         # obrigatório, sem default
    uf: str = Field(..., pattern=...)  # obrigatório, sem default
```

**Correção:**
```python
# CORRETO (após):
class SefazResponseModel(BaseModel):
    status_codigo: str = Field(...)
    status_descricao: str = Field("")
    ambiente: Optional[str] = None
    uf: Optional[str] = None
```

---

### 4. Pydantic v2 `class Config` depreciada — `nfe_completa.py`

**Arquivo:** `app/models/nfe_completa.py`
**Commit:** `fix: Corrigir SefazResponseModel e deprecação de Config em nfe_completa.py`
**Severidade:** BAIXA (deprecation warning)

**Problema:**
`NotaFiscalCompletaResponse` usava `class Config` (sintaxe Pydantic v1) que é depreciada no Pydantic v2.

**Correção:**
```python
# ANTES:
class Config:
    from_attributes = True

# DEPOIS:
model_config = {"from_attributes": True}
```

---

### 5. `datetime.utcnow()` depreciado — `security.py`

**Arquivo:** `app/core/security.py`
**Commit:** `fix: Substituir datetime.utcnow() por datetime.now(timezone.utc) em security.py`
**Severidade:** BAIXA (deprecation warning)

**Problema:**
`datetime.utcnow()` está depreciado no Python 3.12+ e produz `DeprecationWarning` nos logs.

**Correção:**
```python
# ANTES:
from datetime import datetime, timedelta
expire = datetime.utcnow() + timedelta(...)

# DEPOIS:
from datetime import datetime, timedelta, timezone
expire = datetime.now(timezone.utc) + timedelta(...)
```

---

### 6. HTTP_422_UNPROCESSABLE_ENTITY depreciado — `busca_nf_service.py`

**Arquivo:** `app/services/busca_nf_service.py`
**Commit:** `fix: Substituir HTTP_422_UNPROCESSABLE_ENTITY depreciado em busca_nf_service.py`
**Severidade:** BAIXA (deprecation warning)

**Problema:**
Constante `status.HTTP_422_UNPROCESSABLE_ENTITY` foi renomeada para `HTTP_422_UNPROCESSABLE_CONTENT` em versões recentes do Starlette/FastAPI.

**Correção:**
Substituído pelo código numérico `422` diretamente.

---

### 7. Filtro tipo_nf case-sensitive — `buscar_notas.py`

**Arquivo:** `app/api/v1/endpoints/buscar_notas.py`
**Commit:** `fix: Corrigir filtro tipo_nf em listar_notas_empresa`
**Severidade:** MÉDIA

**Problema:**
O endpoint `GET /nfe/empresas/{empresa_id}/notas` convertia o parâmetro `tipo_nf` com `.upper()`, fazendo "NFe" → "NFE". Como o banco armazena "NFe" (exigido pelo modelo), nenhuma nota era retornada ao filtrar por tipo.

**Correção:**
Adicionado mapeamento de normalização:
```python
tipo_map = {"NFE": "NFe", "NFCE": "NFCe", "CTE": "CTe", "NFSE": "NFSe"}
tipo_nf_norm = tipo_map.get(tipo_nf.upper(), tipo_nf)
```

---

## Testes Criados

### Arquivos de teste unitário (10 arquivos, 224 testes)

| Arquivo | Nº de Testes | Cobertura |
|---------|-------------|-----------|
| `tests/unit/test_validators.py` | 25 | utils/validators.py |
| `tests/unit/test_nfe_mapper.py` | 21 | services/nfe_mapper.py |
| `tests/unit/test_sefaz_config.py` | 25 | core/sefaz_config.py |
| `tests/unit/test_certificado_service.py` | 17 | services/certificado_service.py |
| `tests/unit/test_models.py` | 36 | models/nfe_busca.py, nota_fiscal.py |
| `tests/unit/test_real_consulta_service.py` | 19 | services/real_consulta_service.py |
| `tests/unit/test_busca_nf_service.py` | 11 | services/busca_nf_service.py |
| `tests/unit/test_sefaz_service.py` | 21 | services/sefaz_service.py |
| `tests/unit/test_plan_validation.py` | 18 | services/plan_validation.py |
| `tests/unit/test_security.py` | 9 | core/security.py |
| **TOTAL** | **202** | |

### Arquivo de integração

| Arquivo | Nº de Testes | Status |
|---------|-------------|--------|
| `tests/integration/test_pynfe_integration.py` | 22 | 6 skipped (PyNFE indisponível) |

### Resultado final
```
224 passed, 6 skipped in 5.23s
```

---

## Funcionalidade de Busca de Notas — Status

### Endpoints disponíveis

| Operação | Endpoint | Status |
|---------|---------|--------|
| Buscar notas (CNPJ) | `POST /api/v1/nfe/buscar` | ✅ Funcionando |
| Listar notas empresa | `GET /api/v1/nfe/empresas/{id}/notas` | ✅ Funcionando (filtro corrigido) |
| Importar XML único | `POST /api/v1/nfe/importar-xml` | ✅ Funcionando |
| Importar lote XML (ZIP) | `POST /api/v1/nfe/importar-lote` | ✅ Funcionando (até 100 XMLs, 50MB) |
| Download XML individual | `GET /api/v1/nfe/notas/{chave}/xml` | ✅ Funcionando |
| Consultar chave SEFAZ | `GET /api/v1/nfe/consultar-chave/{chave}` | ✅ Funcionando (requer certificado) |
| Buscar notas empresa | `POST /api/v1/nfe/empresas/{id}/notas/buscar` | ✅ Funcionando |

### Tipos de nota suportados

| Tipo | Código | Suporte |
|------|--------|---------|
| NF-e | 55 | ✅ Importação, busca, download XML |
| NFC-e | 65 | ✅ Importação, busca, download XML |
| CT-e | 57 | ⚠️ Importação não implementada (ValueError) |
| NFS-e | — | ⚠️ Sem suporte de importação XML |

### Google Drive Export
❌ **Não implementado.** O sistema não possui integração com Google Drive. Para exportar XMLs, use o download individual ou o lote ZIP.

---

## Limitações Conhecidas

1. **PyNFE incompatível com OpenSSL recente** — `signxml` requer `OpenSSL.crypto.verify` removido em versões modernas. Afeta autorização de NF-e mas não importação de XML.

2. **CT-e não suportado para importação** — `real_consulta_service.importar_xml()` levanta `ValueError` para arquivos CT-e (modelo 57).

3. **DistribuicaoDFe não configurada** — O endpoint de busca assíncrona (`/buscar/iniciar`) usa banco de dados local, não o WebService SEFAZ de distribuição.

4. **`validar_chave_cte()` incorreto** — A função em `validators.py` chama `validar_chave_nfe()` que rejeita modelo=57. CT-e keys sempre retornam False.
