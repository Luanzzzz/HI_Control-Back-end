# 🔍 Análise Técnica Pré-Commit - Hi-Control
**Data:** 10/02/2026  
**Escopo:** Bot + Google Drive + Gestão de Certificados

---

## 📋 RESUMO EXECUTIVO

**Status Geral:** ⚠️ **REQUER AJUSTES** (1 vulnerabilidade crítica de segurança)

### Problemas Críticos Encontrados: 1
### Problemas de Robustez: 3
### Problemas de UX/Clean Code: 2
### Otimizações Sugeridas: 2

---

## 🛡️ 1. SEGURANÇA E PRIVACIDADE DE DADOS

### ❌ **CRÍTICO: Vazamento de Dados - Endpoint `/bot/empresas/{empresa_id}/status`**

**Arquivo:** `app/api/v1/endpoints/bot_status.py` (linhas 165-230)

**Problema:**
O endpoint `obter_status_empresa` não valida se a `empresa_id` pertence ao usuário autenticado antes de buscar as notas. Um usuário pode passar qualquer UUID de empresa e visualizar métricas de empresas de outros escritórios.

**Código Problemático:**
```python
@router.get("/empresas/{empresa_id}/status")
async def obter_status_empresa(
    empresa_id: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    # ❌ FALTA: Validação de propriedade da empresa
    response_ultima = db.table("notas_fiscais")\
        .select("created_at, tipo, numero")\
        .eq("empresa_id", empresa_id)\  # Sem verificar se empresa pertence ao user
        .execute()
```

**Impacto:** 
- **Severidade:** ALTA
- **CVSS Score:** 7.5 (High)
- Um contador pode acessar dados de empresas de outros escritórios

**Correção Necessária:**
```python
@router.get("/empresas/{empresa_id}/status")
async def obter_status_empresa(
    empresa_id: str,
    usuario: dict = Depends(get_current_user),
    db: Client = Depends(get_admin_db)
):
    try:
        user_id = usuario.get("id")
        
        # ✅ VALIDAÇÃO: Verificar se empresa pertence ao usuário
        empresa_check = db.table("empresas")\
            .select("id")\
            .eq("id", empresa_id)\
            .eq("usuario_id", user_id)\
            .eq("ativo", True)\
            .maybe_single()\
            .execute()
        
        if not empresa_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Empresa não encontrada ou não pertence ao seu escritório"
            )
        
        # Agora sim, buscar notas da empresa validada
        response_ultima = db.table("notas_fiscais")\
            .select("created_at, tipo, numero")\
            .eq("empresa_id", empresa_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        # ... resto do código
```

---

### ✅ **APROVADO: Injeção SQL - Supabase Queries**

**Arquivo:** `bot/utils/supabase_client.py`

**Análise:**
Todas as queries utilizam métodos seguros do SDK Supabase (`.eq()`, `.in_()`, `.select()`). Não há concatenação de strings SQL. **Seguro.**

**Exemplo Seguro:**
```python
response = client.table("empresas")\
    .select("*")\
    .eq("ativo", True)\
    .execute()  # ✅ Método seguro do SDK
```

---

### ⚠️ **ATENÇÃO: Sanitização de Nomes de Pastas - Google Drive**

**Arquivo:** `app/services/google_drive_service.py` (linha 357)

**Problema:**
A sanitização de nomes de empresas para pastas usa regex básica, mas pode não cobrir todos os casos edge (emojis, caracteres unicode problemáticos).

**Código Atual:**
```python
empresa_folder_name = re.sub(r'[<>:"/\\|?*]', '_', empresa_nome.strip())
```

**Sugestão de Melhoria:**
```python
# Sanitização mais robusta
def sanitize_folder_name(name: str) -> str:
    # Remove caracteres perigosos
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Remove espaços múltiplos
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    # Limita tamanho (Google Drive tem limite de 255 chars)
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    # Remove trailing dots/spaces (Windows não permite)
    sanitized = sanitized.rstrip('. ')
    return sanitized if sanitized else "Empresa_Sem_Nome"

empresa_folder_name = sanitize_folder_name(empresa_nome)
```

---

## 🔧 2. ROBUSTEZ DA AUTOMAÇÃO

### ✅ **APROVADO: Loop do Bot - Tratamento de Erros por Empresa**

**Arquivo:** `bot/main.py` (linhas 96-111)

**Análise:**
O loop processa cada empresa individualmente com try/except. Se uma empresa falhar, o processamento continua para as outras. **Correto.**

```python
for i, empresa in enumerate(empresas, 1):
    try:
        notas = self._buscar_notas_empresa(empresa)
        total_notas += len(notas)
    except Exception as e:
        logger.error(f"❌ Erro ao processar empresa: {e}", exc_info=True)
        total_erros += 1
        # ✅ Continua para próxima empresa
```

---

### ⚠️ **MELHORIA: Verificação de Duplicidade no Google Drive**

**Arquivo:** `app/services/google_drive_service.py` (linhas 479-502)

**Problema:**
O método `_file_exists_in_folder` verifica apenas pelo **nome do arquivo**, não considera metadados como `chave_acesso` ou hash do conteúdo. Isso pode causar:
- Falsos positivos (arquivo com mesmo nome mas conteúdo diferente)
- Falsos negativos (arquivo com nome diferente mas mesmo conteúdo)

**Código Atual:**
```python
async def _file_exists_in_folder(
    self, client, headers, filename: str, folder_id: str
) -> bool:
    query = (
        f"name='{filename}' and "
        f"'{folder_id}' in parents and "
        f"trashed=false"
    )
    # ❌ Verifica apenas por nome
```

**Sugestão de Melhoria:**
```python
async def _file_exists_in_folder(
    self, client, headers, filename: str, folder_id: str,
    chave_acesso: Optional[str] = None
) -> bool:
    # Buscar por nome
    query = (
        f"name='{filename}' and "
        f"'{folder_id}' in parents and "
        f"trashed=false"
    )
    resp = await client.get(
        "https://www.googleapis.com/drive/v3/files",
        headers=headers,
        params={"q": query, "fields": "files(id,name,description)", "pageSize": 1},
    )
    
    if resp.status_code == 200:
        files = resp.json().get("files", [])
        if files:
            # Se temos chave_acesso, verificar também na description/metadata
            if chave_acesso:
                # Opcional: adicionar chave_acesso na description ao criar arquivo
                # para verificação mais robusta
                pass
            return True
    
    return False
```

**Nota:** Para verificação perfeita, seria necessário armazenar `chave_acesso` nos metadados do arquivo (description ou custom properties).

---

### ⚠️ **MELHORIA: Graceful Degradation - Google Drive Offline**

**Arquivo:** `app/services/google_drive_service.py` (linhas 292-427)

**Problema:**
Não há tratamento explícito de timeout ou retry se o Google Drive estiver temporariamente indisponível. O código apenas retorna `None` em caso de erro, mas não diferencia entre erro temporário e permanente.

**Sugestão de Melhoria:**
```python
async def salvar_xml_no_drive(...) -> Optional[str]:
    try:
        # ... código existente ...
    except httpx.TimeoutException:
        logger.warning(f"Timeout ao salvar XML no Drive para empresa {empresa_id}")
        return None
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (429, 500, 502, 503, 504):
            # Erro temporário - pode tentar novamente depois
            logger.warning(f"Erro temporário do Drive (status {e.response.status_code})")
        else:
            logger.error(f"Erro permanente do Drive: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro ao salvar XML no Drive: {e}", exc_info=True)
        return None
```

---

### ✅ **APROVADO: Estrutura de Pastas Recursiva**

**Arquivo:** `app/services/google_drive_service.py` (linhas 429-477)

**Análise:**
A recursão para criar pastas é eficiente. O método `_get_or_create_folder` busca antes de criar, evitando duplicatas. **Correto.**

---

## 🎨 3. UX E FLUXO "PASSO ÚNICO"

### ✅ **APROVADO: Limpeza de Estado após Upload**

**Arquivo:** `components/Certificados.tsx` (linhas 180-183)

**Análise:**
O componente limpa corretamente o estado após upload bem-sucedido:
- `setCertFile(null)`
- `setCertPassword('')`
- `setSelectedEmpresa(null)`

**Correto.**

---

### ⚠️ **MELHORIA: Mensagens de Erro Mais Descritivas**

**Arquivo:** `components/Certificados.tsx` (linhas 147-161)

**Problema:**
As mensagens de erro são genéricas. Podem ser mais específicas.

**Código Atual:**
```typescript
if (!validateFileExtension(certFile, ['.pfx', '.p12'])) {
  setUploadResult({
    type: 'error',
    message: 'Arquivo deve ser .pfx ou .p12',
  });
  return;
}
```

**Sugestão:**
```typescript
if (!validateFileExtension(certFile, ['.pfx', '.p12'])) {
  const ext = certFile.name.split('.').pop()?.toLowerCase();
  setUploadResult({
    type: 'error',
    message: `Formato inválido: "${ext}". O certificado deve ser um arquivo .pfx ou .p12`,
  });
  return;
}
```

---

### ⚠️ **ATENÇÃO: Re-renders no Dashboard**

**Arquivo:** `components/Dashboard.tsx` (linhas 176-189)

**Problema:**
O `useEffect` que carrega status da empresa depende de `carregarEmpresaStatus`, que é um `useCallback`. Isso está correto, mas há risco de loop se `selectedEmpresaId` mudar rapidamente.

**Análise:**
O código atual está **seguro** porque:
- `carregarEmpresaStatus` é memoizado com `useCallback`
- `selectedEmpresaId` só muda via select manual do usuário
- Há guard clause `if (!empresaId) return`

**Status:** ✅ **APROVADO** (mas monitorar em produção)

---

## 🧹 4. CLEAN CODE E PADRÕES MCP

### ✅ **APROVADO: Rotas RESTful**

**Arquivo:** `app/api/v1/router.py`

**Análise:**
Todas as rotas seguem padrão RESTful:
- `GET /bot/status` ✅
- `GET /bot/empresas/{empresa_id}/status` ✅
- `GET /bot/metricas` ✅
- `POST /bot/sincronizar-agora` ✅

**Correto.**

---

### ⚠️ **LIMPEZA: Console.logs no Frontend**

**Arquivos:** `components/Dashboard.tsx`, `components/Certificados.tsx`

**Problema:**
Há `console.error` e `console.log` espalhados pelo código. Em produção, devem ser removidos ou substituídos por sistema de logging estruturado.

**Encontrados:**
- `Dashboard.tsx`: 4x `console.error` (linhas 127, 141, 153, 168)
- `Certificados.tsx`: 1x `console.error` (linha 132)
- `InvoiceSearch.tsx`: 2x `console.log` (linhas 325-326) - **debug logs**

**Sugestão:**
```typescript
// Criar utility de logging
// utils/logger.ts
export const logger = {
  error: (message: string, error?: any) => {
    if (process.env.NODE_ENV === 'development') {
      console.error(message, error);
    }
    // Em produção, enviar para serviço de logging (Sentry, LogRocket, etc.)
  },
  log: (message: string, ...args: any[]) => {
    if (process.env.NODE_ENV === 'development') {
      console.log(message, ...args);
    }
  }
};

// Substituir todos os console.error por logger.error
```

**Prioridade:** BAIXA (não bloqueia commit, mas deve ser feito antes de produção)

---

### ✅ **APROVADO: Logging Estruturado no Backend**

**Arquivos:** `bot/main.py`, `app/services/google_drive_service.py`

**Análise:**
Todo o backend usa `logger` estruturado do Python. Não há `print()` perdidos nos arquivos modificados (apenas em scripts de teste, que é aceitável).

---

## 📊 5. OTIMIZAÇÕES DE PERFORMANCE

### 💡 **SUGESTÃO: Cache de Status de Certificados**

**Arquivo:** `app/api/v1/endpoints/bot_status.py` (linhas 63-84)

**Problema:**
O cálculo de certificados expirados é feito em loop Python. Para muitas empresas, pode ser lento.

**Sugestão:**
```python
# Usar query SQL para contar certificados expirados
agora = datetime.now().isoformat()
response_cert = db.table("empresas")\
    .select("id", count="exact")\
    .in_("id", empresas_ids)\
    .or_("certificado_a1.is.null,certificado_validade.lt.{agora}".format(agora=agora))\
    .execute()
```

---

### 💡 **SUGESTÃO: Batch Upload para Google Drive**

**Arquivo:** `bot/main.py` (linhas 229-287)

**Problema:**
O upload de XMLs para o Drive é feito sequencialmente, um por vez. Para muitas notas, pode ser lento.

**Sugestão:**
```python
async def _upload_todas():
    # Upload em paralelo (batch de 5 por vez para não exceder rate limits)
    semaphore = asyncio.Semaphore(5)
    
    async def upload_com_semaphore(nota):
        async with semaphore:
            # ... código de upload ...
    
    tasks = [upload_com_semaphore(nota) for nota in notas]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    salvos = sum(1 for r in results if r and not isinstance(r, Exception))
```

**Prioridade:** BAIXA (otimização futura)

---

## ✅ CHECKLIST FINAL

### Segurança
- [x] Filtros por `empresa_id` e `user_id` aplicados
- [x] Queries Supabase usam métodos seguros
- [ ] **FALTA:** Validação de propriedade em `/bot/empresas/{empresa_id}/status`

### Robustez
- [x] Loop do bot não interrompe por erro de uma empresa
- [x] Estrutura de pastas recursiva eficiente
- [ ] **MELHORIA:** Verificação de duplicidade mais robusta no Drive
- [ ] **MELHORIA:** Graceful degradation para Drive offline

### UX
- [x] Senha limpa após upload
- [x] Mensagens de erro exibidas
- [ ] **MELHORIA:** Mensagens de erro mais específicas

### Clean Code
- [x] Rotas RESTful
- [x] Logging estruturado no backend
- [ ] **LIMPEZA:** Remover `console.log` do frontend

---

## 🎯 VEREDICTO FINAL

### ⚠️ **REQUER AJUSTES**

**Bloqueadores para Commit:**
1. ❌ **CRÍTICO:** Adicionar validação de propriedade da empresa no endpoint `/bot/empresas/{empresa_id}/status`

**Recomendações (Não Bloqueiam):**
1. ⚠️ Melhorar sanitização de nomes de pastas no Drive
2. ⚠️ Melhorar verificação de duplicidade no Drive
3. ⚠️ Adicionar graceful degradation para Drive offline
4. 💡 Remover `console.log` do frontend antes de produção
5. 💡 Otimizar batch upload para Drive

---

## 📝 PRÓXIMOS PASSOS

1. **URGENTE:** Corrigir vulnerabilidade de segurança no endpoint de status da empresa
2. **IMPORTANTE:** Implementar melhorias de robustez no Google Drive
3. **OPCIONAL:** Limpar console.logs e otimizar performance

---

**Assinado por:** Análise Técnica Automatizada  
**Data:** 10/02/2026
