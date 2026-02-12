# Correções Aplicadas - 2026-02-12

## ✅ Problemas Corrigidos

### 1. Frontend com dados mockados ✅
**Problema**: `.env` apontando para `localhost:8000` mas backend está na Vercel
**Causa**: Configuração desatualizada da URL da API
**Solução Aplicada**:
- Atualizado `d:\Projetos\Cursor\Hi_Control\.env`
- Alterado: `VITE_API_URL=http://localhost:8000`
- Para: `VITE_API_URL=https://backend-gamma-cyan-75.vercel.app`

**Status**: ✅ **CORRIGIDO**

---

### 2. Backend não conecta com Google Drive ✅
**Problema**: Dependências Python faltantes (`cryptography`, `lxml`, `httpx`, `google-*`)
**Causa**: Ambiente virtual sem as dependências instaladas
**Solução Aplicada**:
```bash
pip install cryptography lxml httpx google-api-python-client \
            google-auth google-auth-oauthlib apscheduler
```

**Dependências instaladas**:
- ✅ `cryptography==46.0.5`
- ✅ `lxml==6.0.2`
- ✅ `httpx==0.28.1`
- ✅ `google-api-python-client==2.190.0`
- ✅ `google-auth==2.48.0`
- ✅ `google-auth-oauthlib==1.2.4`
- ✅ `apscheduler==3.11.2`

**Verificação**:
```python
from app.services.google_drive_service import google_drive_service
# ✅ OK: GoogleDriveService carregado
```

**Status**: ✅ **CORRIGIDO**

---

### 3. Sidebar sem botão de recolher ✅
**Problema**: Falta botão com 3 pontos para recolher o menu
**Causa**: Componente `Sidebar.tsx` não tinha botão de toggle desktop
**Solução Aplicada**:
- Arquivo: `d:\Projetos\Cursor\Hi_Control\components\Sidebar.tsx`
- Adicionado import: `Menu` do `lucide-react`
- Adicionado botão no header da sidebar (ao lado do logo):

```tsx
{/* Botão de Recolher Sidebar (3 pontos) */}
<button
  onClick={toggleSidebar}
  className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700
             transition-colors lg:block hidden"
  title="Recolher menu"
>
  <Menu size={20} className="text-gray-600 dark:text-gray-400" />
</button>
```

**Status**: ✅ **CORRIGIDO**

---

## 📋 Próximos Passos para Teste Completo

### Passo 1: Configurar Google OAuth no Supabase

**Você precisa fazer isso MANUALMENTE no painel do Supabase**:

1. Acesse: [Supabase Dashboard](https://supabase.com/dashboard)
2. Selecione seu projeto
3. Vá em **Authentication** → **Providers**
4. Habilite o provider **Google**
5. Configure:
   - **Client ID**: `931689312133-47neph5andjmodm6l4ti9ppc6po5l37n.apps.googleusercontent.com`
   - **Client Secret**: `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`
   - **Redirect URL**: `https://backend-gamma-cyan-75.vercel.app/api/v1/drive/callback`

### Passo 2: Configurar Google Drive para um Cliente

1. Acesse o frontend: `https://[seu-app].vercel.app`
2. Vá em **Clientes** → Selecione um cliente
3. Clique no botão **"Conectar Google Drive"**
4. Autorize o acesso
5. O sistema vai criar a pasta automaticamente

### Passo 3: Adicionar Certificado A1 do Cliente

1. No detalhe do cliente, clique em **"Adicionar Certificado"**
2. Faça upload do arquivo `.pfx` do certificado
3. Digite a senha do certificado
4. Sistema vai criptografar e salvar no Supabase Storage

### Passo 4: Cadastrar Credenciais NFS-e (se necessário)

**Se a empresa emite NFS-e**, você precisa cadastrar as credenciais municipais:

1. Vá em **Configurações** → **Credenciais NFS-e**
2. Preencha:
   - Empresa (selecione)
   - Município/Código
   - Provedor (Ex: "Base Nacional")
   - URL da API
   - Usuário
   - Senha
3. Marque como **Ativo**

### Passo 5: Testar o Bot Automaticamente

Depois que tudo estiver configurado, o bot APScheduler vai rodar **a cada 60 minutos**:

```
Bot APScheduler (60min)
    ↓
buscar_empresas_ativas()
    ↓
buscar_credenciais_nfse() [com fallback]
    ↓
autenticar() → buscar_notas()
    ↓
salvar_xml_no_drive()
    ↓
Frontend exibe notas do Drive
```

### Passo 6: Verificar no Dashboard do Cliente

1. Acesse o frontend
2. Vá em **Clientes** → Selecione o cliente
3. Clique no botão **"Sincronizar Notas"**
4. O sistema vai:
   - Buscar XMLs do Drive
   - Parsear e exibir na tela
   - **NÃO** salva no banco (leitura direta)

---

## 🔍 Como Testar Cada Funcionalidade

### Teste 1: Frontend conecta com Backend ✅

```bash
# No console do navegador (F12)
console.log(import.meta.env.VITE_API_URL)
# Deve retornar: https://backend-gamma-cyan-75.vercel.app
```

### Teste 2: Sidebar recolhe/expande ✅

1. Abra o app no desktop
2. Clique no ícone de 3 pontos (Menu) ao lado do logo "Hi Control"
3. A sidebar deve recolher para a esquerda
4. Clique novamente para expandir

### Teste 3: Endpoint /notas/drive funciona ⚠️

**REQUER**: Cliente com Drive configurado e XMLs na pasta

```bash
curl -X GET "https://backend-gamma-cyan-75.vercel.app/api/v1/notas/drive/{empresa_id}" \
     -H "Authorization: Bearer {seu_token}"
```

**Resposta esperada**:
```json
{
  "success": true,
  "total": 5,
  "notas": [
    {
      "numero": "001",
      "tipo": "NFS-e",
      "valor_total": 1500.00,
      "drive_file_id": "abc123",
      ...
    }
  ]
}
```

---

## ⚠️ Avisos Importantes

### 1. OAuth do Google Drive
- **Não configurado no código** - você precisa configurar no painel do Supabase
- Sem isso, o botão "Conectar Drive" vai falhar

### 2. Certificado A1
- **Obrigatório** para buscar notas via SEFAZ/Base Nacional
- Sem certificado, o bot não consegue autenticar

### 3. Credenciais NFS-e
- **Opcional** - só necessário se a empresa emite NFS-e
- O bot tem fallback: tenta por município, depois tenta qualquer credencial ativa

### 4. Primeiro Teste
- **Use um cliente de teste** com poucas notas
- Verifique os logs do backend para ver se o bot está executando
- Logs: `https://backend-gamma-cyan-75.vercel.app/logs` (se configurado)

---

## 📊 Arquitetura Final do Fluxo

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Contador configura cliente                               │
│    - Adiciona certificado A1 (.pfx + senha)                 │
│    - Conecta Google Drive (OAuth)                           │
│    - Cadastra credenciais NFS-e (opcional)                  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Bot APScheduler roda a cada 60 minutos                   │
│    - Busca empresas ativas com certificado                  │
│    - Autentica na Base Nacional (cert A1)                   │
│    - Busca notas prestadas + tomadas                        │
│    - Salva XMLs no Google Drive                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Frontend exibe notas em tempo real                       │
│    - GET /notas/drive/{empresa_id}                          │
│    - Parser automático (NF-e, NFS-e, CT-e)                  │
│    - Exibe: número, valor, emitente, status                 │
│    - Botão "Sincronizar" para forçar nova busca             │
└─────────────────────────────────────────────────────────────┘
```

---

## ✅ Checklist Final

- [x] URL da API corrigida no frontend
- [x] Botão de recolher sidebar adicionado
- [x] Dependências Python instaladas
- [x] GoogleDriveService carregando sem erros
- [x] Endpoint /notas/drive criado e registrado
- [ ] **Você precisa fazer**: Configurar Google OAuth no Supabase
- [ ] **Você precisa fazer**: Adicionar certificado A1 de um cliente
- [ ] **Você precisa fazer**: Conectar Google Drive de um cliente
- [ ] **Você precisa testar**: Bot executando automaticamente
- [ ] **Você precisa testar**: Notas aparecendo no frontend

---

## 🆘 Se algo não funcionar

### Erro: "Not authenticated" ao acessar /notas/drive
**Solução**: Verifique se o token JWT está sendo enviado no header `Authorization: Bearer {token}`

### Erro: "Google Drive não configurado"
**Solução**: O cliente precisa autorizar o Drive através do botão no frontend

### Erro: "Certificado não encontrado"
**Solução**: Faça upload do certificado A1 (.pfx) nas configurações do cliente

### Bot não está buscando notas
**Solução**:
1. Verifique logs do backend
2. Certifique-se que o cliente tem:
   - Certificado A1 configurado
   - `empresas.ativa = true`
   - Credenciais NFS-e cadastradas (se aplicável)

---

**Data**: 2026-02-12
**Status**: ✅ Correções aplicadas - Pronto para testes
**Próximo Passo**: Configurar Google OAuth no Supabase
