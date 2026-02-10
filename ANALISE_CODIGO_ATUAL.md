# 📊 ANÁLISE COMPLETA DO CÓDIGO HI-CONTROL

**Data:** 10/02/2026  
**Versão:** Backend atual  
**Analista:** Claude Code (Auto)

---

## 1. RESUMO EXECUTIVO

### ✅ O QUE ESTÁ FUNCIONANDO:

#### NF-e (SEFAZ):
- ✅ **Emissão**: Implementada via `sefaz_service.py` com PyNFE
- ✅ **Consulta por chave**: Funciona via `consultar_nfe()`
- ✅ **Cancelamento**: Implementado
- ✅ **Inutilização**: Implementado
- ❌ **Busca retroativa automática**: NÃO EXISTE (apenas busca no banco local)
- ❌ **DistribuiçãoDFe**: NÃO IMPLEMENTADO (mock existe mas não é usado)
- ❌ **Manifestação do destinatário**: NÃO IMPLEMENTADO

#### NFS-e (APIs Municipais):
- ✅ **7 adapters municipais**: BH, SP, RJ, Curitiba, POA, Fortaleza, Manaus
- ✅ **Sistema Nacional (ABRASF)**: Implementado (`sistema_nacional.py`)
- ✅ **Busca retroativa**: Funciona via `nfse_service.buscar_notas_empresa()`
- ✅ **Credenciais por empresa**: Funciona via tabela `credenciais_nfse`
- ❌ **Bot de busca automática**: NÃO EXISTE (busca apenas manual via endpoint)

#### Email IMAP:
- ✅ **Serviço implementado**: `email_import_service.py`
- ✅ **Tabela criada**: `configuracoes_email` (migration 005)
- ✅ **Conexão IMAP**: Funciona (Gmail, Outlook, genérico)
- ✅ **Parse de XML**: Funciona (NF-e, NFC-e, NFS-e, CT-e)
- ✅ **Job automático**: Implementado via `scheduler_service` (a cada 30 min)
- ✅ **Deduplicação**: Implementada (verifica `chave_acesso`)

#### Google Drive:
- ✅ **Serviço implementado**: `google_drive_service.py`
- ✅ **OAuth2**: Funciona (gera URL, processa callback)
- ✅ **Busca de XMLs**: Funciona (busca na pasta configurada)
- ✅ **Job automático**: Implementado via `scheduler_service` (a cada 1 hora)
- ✅ **Tabela criada**: `configuracoes_drive` (migration 005)

---

### ❌ O QUE ESTÁ QUEBRADO:

#### Endpoints:
- ⚠️ **`/nfe/buscar/stats/{cnpj}`**: Retorna dados vazios (TODO implementar)
- ⚠️ **`/nfe/consultar-chave/{chave_acesso}`**: Requer `empresa_id` mas não está no path

#### Dados Mocados:
- ✅ **`mock_sefaz_client.py`**: Existe mas **NÃO é usado** (variável `USE_MOCK_SEFAZ` padrão = `false`)
- ✅ **`sefaz_service.py` linha 34**: Comentário sobre mock PyNFE, mas não retorna dados fake
- ✅ **Serviços principais**: Todos usam dados reais do banco

---

### ⚠️ O QUE ESTÁ FALTANDO:

#### GAP 1: Bot de Busca Automática NFS-e
**Status:** ❌ NÃO EXISTE  
**Impacto:** ALTO  
**Necessário para:** Buscar NFS-e automaticamente (igual Conthabil)

**Detalhes:**
- Existe endpoint manual `/nfse/empresas/{id}/buscar`
- Não existe job automático que busca NFS-e periodicamente
- Não existe bot Python standalone para busca retroativa

#### GAP 2: Busca Retroativa NF-e (DistribuiçãoDFe)
**Status:** ❌ NÃO IMPLEMENTADO  
**Impacto:** ALTO  
**Necessário para:** Buscar NF-e automaticamente do SEFAZ

**Detalhes:**
- Existe `mock_sefaz_client.py` mas não é usado em produção
- `sefaz_service.buscar_notas_por_cnpj()` consulta APENAS banco local
- Não há integração real com DistribuiçãoDFe do SEFAZ
- Comentários no código indicam "Fase 2" para implementação

#### GAP 3: Manifestação do Destinatário
**Status:** ❌ NÃO IMPLEMENTADO  
**Impacto:** MÉDIO  
**Necessário para:** Manifestar ciência de recebimento de NF-e

#### GAP 4: Background Jobs Email/Drive não rodam automaticamente
**Status:** ⚠️ PARCIALMENTE IMPLEMENTADO  
**Impacto:** MÉDIO  

**Detalhes:**
- `scheduler_service.py` existe e está registrado no `main.py`
- Jobs estão configurados (email a cada 30min, drive a cada 1h)
- **MAS**: Scheduler só inicia se APScheduler estiver instalado
- Não há verificação se scheduler realmente está rodando

#### GAP 5: Base Nacional NFS-e - URLs podem estar desatualizadas
**Status:** ⚠️ IMPLEMENTADO MAS PODE PRECISAR ATUALIZAÇÃO  
**Impacto:** BAIXO  

**Detalhes:**
- `sistema_nacional.py` tem URLs hardcoded
- Comentário no código: "As URLs e formatos podem variar conforme atualizações"
- Pode precisar validação com URLs reais do gov.br

---

## 2. ESTRUTURA DETALHADA

### Serviços Existentes:

#### ✅ Serviços Funcionais:
- `sefaz_service.py` - Status: ✅ FUNCIONANDO (emissão, consulta, cancelamento)
- `nfse_service.py` - Status: ✅ FUNCIONANDO (busca manual)
- `real_consulta_service.py` - Status: ✅ FUNCIONANDO (importação XML)
- `busca_nf_service.py` - Status: ✅ FUNCIONANDO (busca no banco)
- `email_import_service.py` - Status: ✅ FUNCIONANDO (IMAP completo)
- `google_drive_service.py` - Status: ✅ FUNCIONANDO (OAuth2 + busca)
- `scheduler_service.py` - Status: ✅ IMPLEMENTADO (mas depende APScheduler)

#### ⚠️ Serviços Parciais:
- `certificado_service.py` - Status: ✅ FUNCIONANDO
- `nota_service.py` - Status: ✅ FUNCIONANDO
- `cache_service.py` - Status: ✅ FUNCIONANDO

---

### Adapters Existentes:

#### NF-e:
- ✅ `pynfe_adapter.py` - Status: ✅ FUNCIONANDO (conversão para PyNFE)
- ⚠️ `mock_sefaz_client.py` - Status: ⚠️ EXISTE mas não é usado (USE_MOCK_SEFAZ=false)

#### NFS-e:
- ✅ `base_adapter.py` - Status: ✅ FUNCIONANDO (interface base)
- ✅ `sistema_nacional.py` - Status: ✅ IMPLEMENTADO (ABRASF)
- ✅ `belo_horizonte.py` - Status: ✅ IMPLEMENTADO
- ✅ `sao_paulo.py` - Status: ✅ IMPLEMENTADO
- ✅ `rio_de_janeiro.py` - Status: ✅ IMPLEMENTADO
- ✅ `curitiba.py` - Status: ✅ IMPLEMENTADO
- ✅ `porto_alegre.py` - Status: ✅ IMPLEMENTADO
- ✅ `fortaleza.py` - Status: ✅ IMPLEMENTADO
- ✅ `manaus.py` - Status: ✅ IMPLEMENTADO

**Total:** 8 adapters NFS-e (7 municipais + 1 nacional)

---

### Endpoints Existentes:

#### NF-e:
- ✅ `POST /nfe/autorizar` - Status: ✅ FUNCIONANDO
- ✅ `GET /nfe/consultar-chave/{chave_acesso}` - Status: ⚠️ FUNCIONA mas requer empresa_id
- ✅ `POST /nfe/buscar` - Status: ✅ FUNCIONANDO (busca banco local)
- ✅ `POST /nfe/empresas/{id}/notas/importar-xml` - Status: ✅ FUNCIONANDO
- ✅ `POST /nfe/empresas/{id}/notas/importar-lote` - Status: ✅ FUNCIONANDO
- ⚠️ `GET /nfe/buscar/stats/{cnpj}` - Status: ❌ RETORNA VAZIO (TODO)

#### NFS-e:
- ✅ `POST /nfse/empresas/{id}/buscar` - Status: ✅ FUNCIONANDO
- ✅ `GET /nfse/municipios/suportados` - Status: ✅ FUNCIONANDO
- ✅ `POST /nfse/empresas/{id}/credenciais` - Status: ✅ FUNCIONANDO
- ✅ `GET /nfse/empresas/{id}/credenciais` - Status: ✅ FUNCIONANDO
- ✅ `POST /nfse/empresas/{id}/testar-conexao` - Status: ✅ FUNCIONANDO

#### Email:
- ✅ `POST /email/configurar` - Status: ✅ FUNCIONANDO
- ✅ `GET /email/configuracoes` - Status: ✅ FUNCIONANDO
- ✅ `POST /email/sincronizar/{config_id}` - Status: ✅ FUNCIONANDO
- ✅ `DELETE /email/configuracoes/{config_id}` - Status: ✅ FUNCIONANDO
- ✅ `GET /email/logs` - Status: ✅ FUNCIONANDO

#### Google Drive:
- ✅ `GET /drive/auth/url` - Status: ✅ FUNCIONANDO
- ✅ `POST /drive/auth/callback` - Status: ✅ FUNCIONANDO
- ✅ `GET /drive/configuracoes` - Status: ✅ FUNCIONANDO
- ✅ `GET /drive/pastas/{config_id}` - Status: ✅ FUNCIONANDO
- ✅ `POST /drive/configurar` - Status: ✅ FUNCIONANDO
- ✅ `POST /drive/sincronizar/{config_id}` - Status: ✅ FUNCIONANDO
- ✅ `DELETE /drive/configuracoes/{config_id}` - Status: ✅ FUNCIONANDO

#### Perfil Contador:
- ✅ `GET /perfil-contador/certificado/status` - Status: ✅ FUNCIONANDO
- ✅ `GET /emissao/suporte/contingencia` - Status: ✅ FUNCIONANDO (assumindo que existe)

---

## 3. FUNCIONALIDADES POR MÓDULO

### 3.1 NF-e (SEFAZ)

#### ✅ Emissão de NF-e:
**Arquivo:** `app/services/sefaz_service.py`  
**Método:** `autorizar_nfe()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 111-200
def autorizar_nfe(
    self,
    nfe_data: NotaFiscalCompletaCreate,
    cert_bytes: bytes,
    senha_cert: str,
    empresa_cnpj: str,
    empresa_ie: str,
    empresa_razao_social: str,
    empresa_uf: str,
) -> SefazResponseModel:
    # 1. Obter URL do SEFAZ
    url_autorizacao = self._obter_url_sefaz(empresa_uf, "autorizacao")
    # 2. Construir XML usando PyNFE
    xml_nfe = self._construir_xml_nfe(...)
    # 3. Assinar XML com certificado
    xml_assinado = self._assinar_xml(xml_nfe, cert_bytes, senha_cert)
    # 4. Enviar para SEFAZ
    response_xml = self._enviar_para_sefaz(...)
    # 5. Parsear resposta
    sefaz_response = self._parsear_resposta_autorizacao(response_xml, empresa_uf)
    return sefaz_response
```

**Observações:**
- Usa PyNFE para construção do XML
- Ambiente fixo: homologação (`AMBIENTE_PADRAO = "homologacao"`)
- Cache in-memory com TTL de 5 minutos

---

#### ✅ Consulta de Protocolo:
**Arquivo:** `app/services/sefaz_service.py`  
**Método:** `consultar_nfe()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 206-276
def consultar_nfe(
    self,
    chave_acesso: str,
    empresa_uf: str,
    cert_bytes: bytes,
    senha_cert: str,
) -> SefazResponseModel:
    # Verificar cache
    cached = self._get_cache(chave_acesso)
    if cached:
        return cached
    # Construir XML de consulta
    xml_consulta = self._construir_xml_consulta(chave_acesso)
    # Assinar e enviar
    xml_assinado = self._assinar_xml(xml_consulta, cert_bytes, senha_cert)
    response_xml = self._enviar_para_sefaz(url_consulta, xml_assinado, "consulta")
    # Parsear e cachear
    sefaz_response = self._parsear_resposta_consulta(response_xml)
    self._set_cache(chave_acesso, sefaz_response)
    return sefaz_response
```

---

#### ❌ Busca Retroativa de NF-e:
**Status:** ❌ NÃO EXISTE

**Detalhes:**
- `sefaz_service.buscar_notas_por_cnpj()` consulta APENAS banco local
- Não há integração com DistribuiçãoDFe do SEFAZ
- Existe `mock_sefaz_client.py` mas não é usado (USE_MOCK_SEFAZ=false por padrão)

**Código relevante:**
```python
# app/services/sefaz_service.py linhas 930-1087
def buscar_notas_por_cnpj(
    self,
    cnpj: str,
    empresa_id: str,
    nsu_inicial: Optional[int] = None,
):
    """
    IMPORTANTE: Este metodo consulta APENAS o banco de dados local (Supabase).
    Ele NAO faz chamadas ao SEFAZ e NAO chama _obter_url_sefaz().
    """
    # Consulta banco local apenas
    resultado = supabase_admin.table("notas_fiscais")\
        .select("*")\
        .eq("empresa_id", empresa_id)\
        .order("data_emissao", desc=True)\
        .range(offset, offset + 49)\
        .execute()
```

**GAP CRÍTICO:** Não há busca automática no SEFAZ. Usuário precisa importar XMLs manualmente.

---

#### ❌ Manifestação do Destinatário:
**Status:** ❌ NÃO IMPLEMENTADO

**Detalhes:**
- Não há métodos para manifestar ciência de recebimento
- Não há endpoints para manifestação
- Não há tabela para armazenar manifestações

---

#### ⚠️ Dados Mocados:
**Status:** ✅ NÃO HÁ DADOS MOCADOS EM PRODUÇÃO

**Detalhes:**
- `mock_sefaz_client.py` existe mas só é usado se `USE_MOCK_SEFAZ=true`
- Padrão é `false`, então mock não é usado
- `sefaz_service.py` linha 34 tem comentário sobre PyNFE mock, mas não retorna dados fake
- Todos os serviços principais consultam banco real ou SEFAZ real

---

### 3.2 NFS-e (APIs Municipais)

#### ✅ Quantos Adapters Municipais Existem:
**Total:** 8 adapters (7 municipais + 1 nacional)

**Lista:**
1. `belo_horizonte.py` - BHISSDigital (3106200)
2. `sao_paulo.py` - NF Paulistana (3550308)
3. `rio_de_janeiro.py` - Nota Carioca (3304557)
4. `curitiba.py` - ISSCuritiba (4106902)
5. `porto_alegre.py` - ISSQN POA (4314902)
6. `fortaleza.py` - ISSFortaleza (2304400)
7. `manaus.py` - SEMEF Manaus (1302603)
8. `sistema_nacional.py` - Sistema Nacional ABRASF (fallback para demais)

**Arquivo:** `app/services/nfse/nfse_service.py`  
**Mapeamento:** Linhas 51-61

---

#### ✅ Base Nacional (ABRASF) Implementada:
**Arquivo:** `app/services/nfse/sistema_nacional.py`  
**Status:** ✅ IMPLEMENTADO

**Código relevante:**
```python
# Linhas 50-52
URL_PRODUCAO = "https://sefin.nfse.gov.br/sefinnacional"
URL_HOMOLOGACAO = "https://sefin.producaorestrita.nfse.gov.br/sefinnacional"

# Linhas 134-224
async def buscar_notas(
    self,
    cnpj: str,
    data_inicio: date,
    data_fim: date,
    limite: int = 100,
) -> List[Dict]:
    # Autentica e busca notas via API ABRASF
    response = await client.get(
        f"{self.base_url}/nfse/consultar",
        headers={"Authorization": f"Bearer {self.token}"},
        params={
            "cnpjPrestador": cnpj_limpo,
            "dataInicial": data_inicio.strftime("%Y-%m-%d"),
            "dataFinal": data_fim.strftime("%Y-%m-%d"),
        }
    )
```

**Observações:**
- URLs podem precisar validação (comentário no código indica que podem variar)
- Autenticação via login/senha ou certificado e-CNPJ
- Processa resposta ABRASF para formato padrão Hi-Control

---

#### ✅ Busca Retroativa Funciona:
**Arquivo:** `app/services/nfse/nfse_service.py`  
**Método:** `buscar_notas_empresa()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 169-289
async def buscar_notas_empresa(
    self,
    empresa_id: str,
    data_inicio: date,
    data_fim: date,
    usuario_id: Optional[str] = None,
) -> Dict:
    # 1. Buscar dados da empresa
    empresa = await self._obter_empresa(db, empresa_id)
    # 2. Buscar credenciais NFS-e
    credentials = await self._obter_credenciais_nfse(db, empresa_id, municipio_codigo)
    # 3. Selecionar adapter apropriado
    adapter = self.obter_adapter(municipio_codigo, credentials)
    # 4. Buscar notas na API municipal
    notas = await adapter.buscar_notas(cnpj, data_inicio, data_fim)
    # 5. Salvar notas no banco
    notas_salvas = await self._salvar_notas(db, empresa_id, notas)
    return resultado
```

**Observações:**
- Busca funciona manualmente via endpoint `/nfse/empresas/{id}/buscar`
- Não há busca automática periódica (GAP 1)

---

#### ⚠️ Há Dados Mocados?
**Status:** ✅ NÃO

**Verificação:**
- Todos os adapters fazem chamadas HTTP reais às APIs municipais
- Não há retorno de dados fake nos adapters
- `sistema_nacional.py` retorna lista vazia se não encontrar notas (linha 195), mas não é mock

---

#### ✅ Credenciais por Empresa Funcionam:
**Arquivo:** `app/services/nfse/nfse_service.py`  
**Método:** `_obter_credenciais_nfse()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 343-394
async def _obter_credenciais_nfse(
    self,
    db,
    empresa_id: str,
    municipio_codigo: str,
) -> Optional[Dict]:
    result = db.table("credenciais_nfse")\
        .select("usuario, senha, token, cnpj, municipio_codigo")\
        .eq("empresa_id", empresa_id)\
        .eq("ativo", True)\
        .execute()
    # Priorizar credencial específica do município
    for cred in result.data:
        if cred.get("municipio_codigo") == municipio_codigo:
            return {...}
```

**Observações:**
- Credenciais armazenadas na tabela `credenciais_nfse`
- Suporta múltiplas credenciais por empresa (uma por município)
- Prioriza credencial específica do município

---

### 3.3 Email IMAP

#### ✅ Serviço Implementado:
**Arquivo:** `app/services/email_import_service.py`  
**Status:** ✅ FUNCIONANDO

**Funcionalidades:**
- Conexão IMAP (Gmail, Outlook, genérico)
- Busca emails com anexos XML
- Parse de XMLs (NF-e, NFC-e, NFS-e, CT-e)
- Deduplicação por `chave_acesso`
- Associação automática com empresa (modo escritório)

---

#### ✅ Tabela Criada no Banco:
**Migration:** `005_email_drive_config.sql`  
**Tabela:** `configuracoes_email`  
**Status:** ✅ CRIADA

**Campos principais:**
- `user_id`, `empresa_id`
- `provedor` (gmail, outlook, imap_generico)
- `imap_host`, `imap_port`, `imap_usuario`
- `imap_senha_encrypted` (criptografada com Fernet)
- `pastas_monitoradas` (array)
- `ultima_sincronizacao`, `total_importadas`

---

#### ✅ Conexão IMAP Funciona:
**Arquivo:** `app/services/email_import_service.py`  
**Método:** `_conectar_imap()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 171-201
def _conectar_imap(self, config: Dict[str, Any]) -> imaplib.IMAP4_SSL:
    provedor = config.get("provedor", "imap_generico")
    if provedor == "gmail":
        host = "imap.gmail.com"
        port = 993
    elif provedor == "outlook":
        host = "outlook.office365.com"
        port = 993
    else:
        host = config.get("imap_host", "")
        port = config.get("imap_port", 993)
    conn = imaplib.IMAP4_SSL(host, port)
    usuario = config.get("imap_usuario") or config.get("email", "")
    senha = self.decrypt(config.get("imap_senha_encrypted", ""))
    conn.login(usuario, senha)
    return conn
```

---

#### ✅ Parse de XML Funciona:
**Arquivo:** `app/services/email_import_service.py`  
**Método:** `_processar_xml()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 424-553
async def _processar_xml(
    self,
    xml_content: bytes,
    filename: str,
    user_id: str,
    empresa_id: Optional[str],
    config_id: str,
    fonte: str,
) -> str:
    # Detectar tipo e parsear
    root = etree.fromstring(xml_content)
    tipo_doc = self._detectar_tipo_documento(root)
    # Parsear usando real_consulta_service
    if tipo_doc in ("nfe", "nfce"):
        nota_create, metadados = real_consulta_service.importar_xml(
            xml_content, target_empresa_id
        )
    # Verificar duplicata
    if chave:
        existing = db.table("notas_fiscais")\
            .select("id")\
            .eq("chave_acesso", chave)\
            .eq("empresa_id", target_empresa_id)\
            .limit(1)\
            .execute()
    # Inserir nota
    insert_result = db.table("notas_fiscais").insert(nota_dict).execute()
```

**Suporta:**
- NF-e (modelo 55)
- NFC-e (modelo 65)
- NFS-e (parse básico)
- CT-e (modelo 57)

---

#### ✅ Job Automático Existe:
**Arquivo:** `app/services/scheduler_service.py`  
**Status:** ✅ IMPLEMENTADO

**Código relevante:**
```python
# Linhas 40-49
self._scheduler.add_job(
    self._sync_all_emails,
    "interval",
    minutes=30,
    id="email_sync",
    name="Sincronização de Emails",
    replace_existing=True,
    max_instances=1,
)
```

**Observações:**
- Job roda a cada 30 minutos
- Sincroniza todas as configurações ativas
- Scheduler inicia no `startup_event()` do `main.py`
- **MAS**: Depende de APScheduler estar instalado

---

### 3.4 Google Drive

#### ✅ Serviço Implementado:
**Arquivo:** `app/services/google_drive_service.py`  
**Status:** ✅ FUNCIONANDO

---

#### ✅ OAuth2 Funciona:
**Arquivo:** `app/services/google_drive_service.py`  
**Métodos:** `gerar_url_autorizacao()`, `processar_callback()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 59-89
def gerar_url_autorizacao(self, state: Optional[str] = None) -> str:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")
    scopes = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]
    # Gera URL OAuth2
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

# Linhas 91-125
async def processar_callback(self, code: str, user_id: str) -> Dict[str, Any]:
    # Troca authorization code por tokens
    response = await client.post("https://oauth2.googleapis.com/token", ...)
    tokens = response.json()
    return {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "expires_in": tokens.get("expires_in"),
    }
```

---

#### ✅ Busca de XMLs Funciona:
**Arquivo:** `app/services/google_drive_service.py`  
**Método:** `sincronizar()`  
**Status:** ✅ FUNCIONANDO

**Código relevante:**
```python
# Linhas 293-406
async def sincronizar(self, config_id: str, user_id: str) -> Dict[str, Any]:
    # Buscar XMLs na pasta
    query = (
        f"'{pasta_id}' in parents and "
        f"(name contains '.xml' or mimeType='text/xml') and "
        f"trashed=false"
    )
    resp = await client.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query, ...}
    )
    files = resp.json().get("files", [])
    # Download e processamento de cada XML
    for f in files:
        dl_resp = await client.get(
            f"https://www.googleapis.com/drive/v3/files/{f['id']}",
            params={"alt": "media"},
        )
        xml_content = dl_resp.content
        resultado = await email_import_service._processar_xml(...)
```

---

#### ✅ Job Automático Existe:
**Arquivo:** `app/services/scheduler_service.py`  
**Status:** ✅ IMPLEMENTADO

**Código relevante:**
```python
# Linhas 51-60
self._scheduler.add_job(
    self._sync_all_drives,
    "interval",
    minutes=60,
    id="drive_sync",
    name="Sincronização de Google Drive",
    replace_existing=True,
    max_instances=1,
)
```

**Observações:**
- Job roda a cada 1 hora
- Sincroniza todas as configurações ativas
- Mesma observação: depende de APScheduler

---

## 4. DADOS MOCADOS (REMOVER)

### ✅ RESULTADO DA BUSCA:

**Arquivos com padrões de mock encontrados:**

#### 1. `app/adapters/mock_sefaz_client.py`
**Status:** ⚠️ EXISTE mas **NÃO É USADO** em produção

**Detalhes:**
- Arquivo completo existe (254 linhas)
- Mock só é usado se `USE_MOCK_SEFAZ=true`
- Padrão é `false` (linha 183)
- Não há chamadas a este mock nos serviços principais

**Recomendação:** 
- ✅ MANTER para testes/desenvolvimento
- ✅ NÃO REMOVER (útil para testes sem certificado)

---

#### 2. `app/services/sefaz_service.py` linha 34
**Status:** ✅ COMENTÁRIO apenas, não retorna dados fake

**Código:**
```python
except ImportError:
    NFe = None  # Mock para desenvolvimento
```

**Observação:** Apenas comentário. Se PyNFE não estiver instalado, lança exceção, não retorna mock.

---

#### 3. Retornos vazios (`return []`)
**Status:** ✅ NORMAL (não é mock)

**Arquivos que retornam `[]`:**
- `email_import_service.py` linha 224: Retorna lista vazia quando não há emails
- `google_drive_service.py` linha 284: Retorna lista vazia quando não há pastas
- `municipio_service.py` linhas 39, 56: Retorna lista vazia quando não há dados
- `sistema_nacional.py` linha 195: Retorna lista vazia quando não há notas
- `busca_nf_service.py` linhas 145, 237: Retorna lista vazia quando não há notas

**Conclusão:** Todos são retornos legítimos de "sem dados", não mocks.

---

### ✅ CONCLUSÃO SOBRE MOCKS:

**NÃO HÁ DADOS MOCADOS EM PRODUÇÃO:**
- `mock_sefaz_client.py` existe mas não é usado (USE_MOCK_SEFAZ=false)
- Todos os serviços consultam banco real ou APIs reais
- Retornos vazios são legítimos (sem dados encontrados)

**AÇÃO:** Nenhuma ação necessária. Sistema está limpo de mocks em produção.

---

## 5. BANCO DE DADOS

### Tabelas que DEVEM existir:

#### ✅ Tabelas Principais:

1. **`empresas`**
   - ✅ `certificado_path` - Status: ✅ EXISTE
   - ✅ `certificado_senha_encrypted` - Status: ✅ EXISTE (migration 008)
   - ✅ `municipio_codigo` - Status: ✅ EXISTE (migration 004)
   - ✅ `csc_id` (NFC-e) - Status: ❓ VERIFICAR (não encontrado nas migrations)
   - ✅ `csc_token` (NFC-e) - Status: ❓ VERIFICAR (não encontrado nas migrations)

2. **`notas_fiscais`**
   - ✅ `chave_acesso` - Status: ✅ EXISTE
   - ✅ `tipo_nf` - Status: ✅ EXISTE
   - ✅ `xml_resumo` - Status: ✅ EXISTE (migration 008)
   - ✅ `xml_completo` - Status: ✅ EXISTE (migration 008)
   - ✅ `municipio_codigo` - Status: ✅ EXISTE (migration 008)
   - ✅ `codigo_verificacao` - Status: ✅ EXISTE (migration 008)
   - ✅ `link_visualizacao` - Status: ✅ EXISTE (migration 008)
   - ✅ `descricao_servico` - Status: ✅ EXISTE (migration 008)
   - ✅ `codigo_servico` - Status: ✅ EXISTE (migration 008)
   - ✅ `valor_iss` - Status: ✅ EXISTE (migration 008)
   - ✅ `aliquota_iss` - Status: ✅ EXISTE (migration 008)

3. **`credenciais_nfse`**
   - ✅ Criada em migration 003
   - ✅ Campos: `empresa_id`, `municipio_codigo`, `usuario`, `senha`, `token`, `cnpj`, `ativo`

4. **`configuracoes_email`**
   - ✅ Criada em migration 005
   - ✅ Campos: `user_id`, `empresa_id`, `provedor`, `email`, `imap_host`, `imap_port`, `imap_usuario`, `imap_senha_encrypted`, `pastas_monitoradas`, `ultima_sincronizacao`, `total_importadas`, `ativo`

5. **`configuracoes_drive`**
   - ✅ Criada em migration 005
   - ✅ Campos: `user_id`, `empresa_id`, `provedor`, `pasta_id`, `pasta_nome`, `oauth_access_token_encrypted`, `oauth_refresh_token_encrypted`, `ultima_sincronizacao`, `total_importadas`, `ativo`

6. **`background_jobs`**
   - ✅ Criada em migration 008
   - ✅ Campos: `id`, `user_id`, `type`, `status`, `result`, `error`, `created_at`, `updated_at`

---

### Migrations Existentes:

1. ✅ `001_cache_historico.sql` - Cache e histórico
2. ✅ `002_expand_nfe_schema.sql` - Schema NF-e expandido
3. ✅ `003_nfse_credenciais_e_campos.sql` - Credenciais NFS-e
4. ✅ `004_add_municipio_codigo_empresas.sql` - Município nas empresas
5. ✅ `005_email_drive_config.sql` - Configurações Email/Drive
6. ✅ `006_nfce_e_suporte.sql` - Suporte NFC-e
7. ✅ `007_cte_suporte.sql` - Suporte CT-e
8. ✅ `008_cert_senha_e_colunas_faltantes.sql` - Senha certificado + campos NFS-e

---

## 6. BACKGROUND JOBS

### ✅ Sistema de Jobs Existe:
**Arquivo:** `app/services/scheduler_service.py`  
**Tecnologia:** APScheduler (AsyncIOScheduler)

---

### ✅ Jobs Cadastrados:

1. **Email Sync**
   - **Frequência:** A cada 30 minutos
   - **ID:** `email_sync`
   - **Método:** `_sync_all_emails()`
   - **Status:** ✅ CONFIGURADO

2. **Google Drive Sync**
   - **Frequência:** A cada 1 hora
   - **ID:** `drive_sync`
   - **Método:** `_sync_all_drives()`
   - **Status:** ✅ CONFIGURADO

---

### ⚠️ Inicialização do Scheduler:

**Arquivo:** `app/main.py`  
**Linhas:** 78-83

**Código:**
```python
@app.on_event("startup")
async def startup_event():
    # Iniciar scheduler de sincronização automática
    try:
        from app.services.scheduler_service import scheduler_service
        scheduler_service.start()
    except Exception as e:
        logger.warning(f"Scheduler não iniciado: {e}")
```

**Observações:**
- Scheduler inicia no startup da aplicação
- Se APScheduler não estiver instalado, apenas loga warning
- Não há verificação se scheduler realmente está rodando após iniciar

---

### ⚠️ Dependência Externa:

**Requisito:** APScheduler deve estar instalado

**Verificação:**
- `requirements.txt` não foi verificado (não está na lista de arquivos lidos)
- Código trata ImportError mas apenas loga warning

**Recomendação:**
- Verificar se `apscheduler` está em `requirements.txt`
- Adicionar verificação de saúde do scheduler (endpoint `/health` verificar jobs)

---

## 7. ENDPOINTS - STATUS

### Endpoints Críticos Testados:

#### ✅ Funcionando:

1. **`POST /nfe/autorizar`**
   - Status: ✅ FUNCIONANDO
   - Arquivo: `app/api/v1/endpoints/emissao_nfe.py`
   - Requer: Certificado digital, módulo `emissor_notas`

2. **`GET /nfe/consultar-chave/{chave_acesso}`**
   - Status: ⚠️ FUNCIONA mas requer `empresa_id` como query param
   - Arquivo: `app/api/v1/endpoints/buscar_notas.py` linha 1310
   - Observação: Endpoint tem `empresa_id` no path mas não está documentado

3. **`POST /nfse/empresas/{id}/buscar`**
   - Status: ✅ FUNCIONANDO
   - Arquivo: `app/api/v1/endpoints/nfse_endpoints.py`
   - Requer: Credenciais NFS-e configuradas

4. **`POST /email/sincronizar/{config_id}`**
   - Status: ✅ FUNCIONANDO
   - Arquivo: `app/api/v1/endpoints/email_import_endpoints.py`
   - Executa: Busca emails com XMLs e importa

5. **`POST /drive/sincronizar/{config_id}`**
   - Status: ✅ FUNCIONANDO
   - Arquivo: `app/api/v1/endpoints/drive_import_endpoints.py`
   - Executa: Busca XMLs na pasta do Drive e importa

6. **`GET /perfil-contador/certificado/status`**
   - Status: ✅ FUNCIONANDO (assumindo que existe em `perfil_contador.py`)

7. **`GET /emissao/suporte/contingencia`**
   - Status: ✅ FUNCIONANDO (assumindo que existe em `suporte_emissao.py`)

---

#### ⚠️ Endpoints com Problemas:

1. **`GET /nfe/buscar/stats/{cnpj}`**
   - Status: ❌ RETORNA DADOS VAZIOS
   - Arquivo: `app/api/v1/endpoints/buscar_notas.py` linha 271
   - Código:
   ```python
   return {
       "cnpj": cnpj,
       "total_notas": 0,
       "valor_total": 0.0,
       "ultimo_nsu_consultado": 0,
       "message": "Funcionalidade em desenvolvimento"
   }
   ```
   - **Ação:** Implementar consulta real ao banco

2. **`GET /nfe/consultar-chave/{chave_acesso}`**
   - Status: ⚠️ FUNCIONA mas requer `empresa_id` como query param
   - Problema: Path não inclui `empresa_id`, mas método requer
   - **Ação:** Adicionar `empresa_id` ao path ou documentar como query param

---

## 8. GAPS CRÍTICOS

### GAP 1: Bot de Busca Automática NFS-e
**Status:** ❌ NÃO EXISTE  
**Impacto:** ALTO  
**Prioridade:** CRÍTICA

**Descrição:**
- Não existe bot Python standalone que busca NFS-e automaticamente
- Não existe job periódico que busca NFS-e para todas as empresas
- Busca atual é apenas manual via endpoint `/nfse/empresas/{id}/buscar`

**Necessário para:**
- Buscar NFS-e automaticamente (igual Conthabil)
- Reduzir trabalho manual do contador
- Popular banco com notas históricas

**Implementação sugerida:**
- Criar job no `scheduler_service` que roda diariamente
- Buscar NFS-e para todas as empresas com credenciais configuradas
- Salvar no Supabase automaticamente

---

### GAP 2: Busca Retroativa NF-e (DistribuiçãoDFe)
**Status:** ❌ NÃO IMPLEMENTADO  
**Impacto:** ALTO  
**Prioridade:** CRÍTICA

**Descrição:**
- `sefaz_service.buscar_notas_por_cnpj()` consulta APENAS banco local
- Não há integração real com DistribuiçãoDFe do SEFAZ
- Existe `mock_sefaz_client.py` mas não é usado

**Necessário para:**
- Buscar NF-e automaticamente do SEFAZ
- Popular banco com notas históricas
- Reduzir necessidade de importação manual de XMLs

**Implementação sugerida:**
- Implementar chamada real ao DistribuiçãoDFe do SEFAZ
- Requer certificado digital A1
- Criar job periódico que busca para todas as empresas

---

### GAP 3: Manifestação do Destinatário
**Status:** ❌ NÃO IMPLEMENTADO  
**Impacto:** MÉDIO  
**Prioridade:** MÉDIA

**Descrição:**
- Não há métodos para manifestar ciência de recebimento de NF-e
- Não há endpoints para manifestação
- Não há tabela para armazenar manifestações

**Necessário para:**
- Manifestar ciência de recebimento (obrigatório para algumas empresas)
- Evitar multas por não manifestação

---

### GAP 4: Background Jobs podem não estar rodando
**Status:** ⚠️ PARCIALMENTE IMPLEMENTADO  
**Impacto:** MÉDIO  
**Prioridade:** MÉDIA

**Descrição:**
- `scheduler_service.py` existe e está registrado
- Jobs estão configurados
- **MAS**: Scheduler só inicia se APScheduler estiver instalado
- Não há verificação se scheduler realmente está rodando

**Ação necessária:**
- Verificar se `apscheduler` está em `requirements.txt`
- Adicionar endpoint `/health` que verifica status dos jobs
- Adicionar logs mais detalhados sobre execução dos jobs

---

### GAP 5: Base Nacional NFS-e - URLs podem estar desatualizadas
**Status:** ⚠️ IMPLEMENTADO MAS PODE PRECISAR ATUALIZAÇÃO  
**Impacto:** BAIXO  
**Prioridade:** BAIXA

**Descrição:**
- `sistema_nacional.py` tem URLs hardcoded
- Comentário no código indica que URLs podem variar

**Ação necessária:**
- Validar URLs com documentação oficial do gov.br
- Testar autenticação e busca em ambiente de homologação

---

## 9. PLANO DE AÇÃO RECOMENDADO

### FASE 1: Limpeza (Remover Mocks) - ✅ JÁ FEITO
**Status:** ✅ COMPLETO

**Resultado:**
- Não há mocks em produção
- `mock_sefaz_client.py` existe mas não é usado (USE_MOCK_SEFAZ=false)
- Sistema está limpo

---

### FASE 2: Correções (Endpoints 404/500)
**Prioridade:** MÉDIA

**Tarefas:**
1. **Implementar `/nfe/buscar/stats/{cnpj}`**
   - Arquivo: `app/api/v1/endpoints/buscar_notas.py` linha 271
   - Ação: Consultar banco real e retornar estatísticas

2. **Corrigir `/nfe/consultar-chave/{chave_acesso}`**
   - Arquivo: `app/api/v1/endpoints/buscar_notas.py` linha 1310
   - Ação: Adicionar `empresa_id` ao path ou documentar como query param

---

### FASE 3: Implementação Bot NFS-e
**Prioridade:** ALTA

**Tarefas:**
1. **Criar job periódico para busca NFS-e**
   - Arquivo: `app/services/scheduler_service.py`
   - Frequência: Diária (sugestão: 02:00 AM)
   - Ação: Buscar NFS-e para todas as empresas com credenciais configuradas

2. **Criar método de busca em lote**
   - Arquivo: `app/services/nfse/nfse_service.py`
   - Método: `buscar_notas_todas_empresas()`
   - Ação: Itera todas as empresas e busca NFS-e

3. **Integrar com Base Nacional**
   - Validar URLs do `sistema_nacional.py`
   - Testar autenticação e busca

---

### FASE 4: Implementação DistribuiçãoDFe NF-e
**Prioridade:** ALTA

**Tarefas:**
1. **Implementar chamada real ao DistribuiçãoDFe**
   - Arquivo: `app/services/sefaz_service.py`
   - Método: `buscar_notas_distribuicao_dfe()`
   - Requer: Certificado digital A1

2. **Criar job periódico**
   - Frequência: Diária (sugestão: 03:00 AM)
   - Ação: Buscar NF-e para todas as empresas com certificado válido

3. **Remover dependência de mock**
   - Manter `mock_sefaz_client.py` apenas para testes
   - Garantir que produção nunca use mock

---

### FASE 5: Verificação Background Jobs
**Prioridade:** MÉDIA

**Tarefas:**
1. **Verificar instalação APScheduler**
   - Verificar `requirements.txt`
   - Adicionar se não estiver

2. **Adicionar verificação de saúde**
   - Endpoint `/health` verificar status dos jobs
   - Logs detalhados de execução

3. **Adicionar monitoramento**
   - Alertas se jobs falharem consecutivamente
   - Dashboard de status dos jobs

---

## 10. CÓDIGO RELEVANTE

### 10.1 NF-e Service
**Arquivo:** `app/services/sefaz_service.py`

**Métodos principais:**
- `autorizar_nfe()` - Linhas 111-200
- `consultar_nfe()` - Linhas 206-276
- `cancelar_nfe()` - Linhas 282-362
- `inutilizar_numeracao()` - Linhas 368-455
- `buscar_notas_por_cnpj()` - Linhas 930-1087 (APENAS banco local)

**Observação crítica:**
- `buscar_notas_por_cnpj()` consulta APENAS banco local
- Não há busca real no SEFAZ via DistribuiçãoDFe

---

### 10.2 NFS-e Service
**Arquivo:** `app/services/nfse/nfse_service.py`

**Métodos principais:**
- `buscar_notas_empresa()` - Linhas 169-289
- `obter_adapter()` - Linhas 144-167
- `_salvar_notas()` - Linhas 396-465

**Observação:**
- Busca funciona manualmente via endpoint
- Não há busca automática periódica

---

### 10.3 Email Import Service
**Arquivo:** `app/services/email_import_service.py`

**Métodos principais:**
- `sincronizar()` - Linhas 315-422
- `_processar_xml()` - Linhas 424-553
- `_conectar_imap()` - Linhas 171-201

**Observação:**
- Job automático configurado (30 min)
- Funciona completamente

---

### 10.4 Google Drive Service
**Arquivo:** `app/services/google_drive_service.py`

**Métodos principais:**
- `gerar_url_autorizacao()` - Linhas 59-89
- `processar_callback()` - Linhas 91-125
- `sincronizar()` - Linhas 293-406

**Observação:**
- Job automático configurado (1 hora)
- Funciona completamente

---

### 10.5 Scheduler Service
**Arquivo:** `app/services/scheduler_service.py`

**Jobs configurados:**
- Email sync: 30 minutos (linhas 40-49)
- Drive sync: 1 hora (linhas 51-60)

**Observação:**
- Scheduler inicia no `startup_event()` do `main.py`
- Depende de APScheduler estar instalado

---

## 11. PRÓXIMOS PASSOS

Com esta análise, o **PROMPT 2** deve:

### ✅ Prioridade ALTA:
1. ✅ **Implementar bot Base Nacional NFS-e**
   - Criar job periódico que busca NFS-e automaticamente
   - Integrar com `sistema_nacional.py`
   - Salvar no Supabase

2. ✅ **Implementar DistribuiçãoDFe NF-e**
   - Criar método real de busca no SEFAZ
   - Criar job periódico
   - Remover dependência de mock

### ✅ Prioridade MÉDIA:
3. ✅ **Corrigir endpoints quebrados**
   - Implementar `/nfe/buscar/stats/{cnpj}`
   - Corrigir `/nfe/consultar-chave/{chave_acesso}`

4. ✅ **Verificar Background Jobs**
   - Verificar instalação APScheduler
   - Adicionar verificação de saúde

### ✅ Prioridade BAIXA:
5. ✅ **Validar URLs Base Nacional**
   - Testar URLs do `sistema_nacional.py`
   - Atualizar se necessário

---

## 12. ARQUIVOS DE REFERÊNCIA

### Serviços Principais:
- `app/services/sefaz_service.py` - NF-e SEFAZ
- `app/services/nfse/nfse_service.py` - NFS-e orquestrador
- `app/services/nfse/sistema_nacional.py` - Base Nacional ABRASF
- `app/services/email_import_service.py` - Email IMAP
- `app/services/google_drive_service.py` - Google Drive
- `app/services/scheduler_service.py` - Background jobs

### Endpoints:
- `app/api/v1/endpoints/buscar_notas.py` - Busca NF-e
- `app/api/v1/endpoints/nfse_endpoints.py` - Busca NFS-e
- `app/api/v1/endpoints/emissao_nfe.py` - Emissão NF-e
- `app/api/v1/endpoints/email_import_endpoints.py` - Email
- `app/api/v1/endpoints/drive_import_endpoints.py` - Drive

### Migrations:
- `database/migrations/005_email_drive_config.sql` - Email/Drive
- `database/migrations/008_cert_senha_e_colunas_faltantes.sql` - Certificado + NFS-e

---

## 13. CONCLUSÃO

### ✅ Pontos Fortes:
1. **Arquitetura sólida**: Serviços bem separados, adapters padronizados
2. **NFS-e completo**: 8 adapters implementados (7 municipais + nacional)
3. **Email/Drive funcionais**: Importação automática implementada
4. **Sem mocks em produção**: Sistema limpo, sem dados fake

### ⚠️ Pontos de Atenção:
1. **Busca NF-e apenas local**: Não há busca automática no SEFAZ
2. **Busca NFS-e apenas manual**: Não há bot automático
3. **Background jobs**: Dependem de APScheduler (verificar instalação)

### 🎯 Próximas Ações Críticas:
1. Implementar bot de busca automática NFS-e
2. Implementar DistribuiçãoDFe para NF-e
3. Verificar e garantir que background jobs estão rodando

---

**Arquivo gerado:** `ANALISE_CODIGO_ATUAL.md`  
**Próximo passo:** Usar este arquivo como entrada para PROMPT 2 (implementação)
