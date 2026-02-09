# 🧪 Guia de Teste - Sistema NFS-e

## 📋 Pré-requisitos

1. ✅ Migration `003_nfse_credenciais_e_campos.sql` executada
2. ✅ Migration `004_add_municipio_codigo_empresas.sql` executada
3. ✅ Empresa cadastrada no sistema
4. ✅ Credenciais NFS-e da prefeitura (login/senha)

---

## ⚠️ IMPORTANTE: Diferença entre Certificado A1 e Credenciais NFS-e

- **Certificado A1**: Usado para **NF-e** (SEFAZ estadual) - já cadastrado ✅
- **Credenciais NFS-e**: Login/senha da **API municipal** - precisa cadastrar ⚠️

São sistemas diferentes! O certificado A1 não funciona para NFS-e.

---

## 🔧 Passo 1: Configurar Município da Empresa

Execute no **Supabase SQL Editor**:

```sql
-- Substitua <empresa_id> pelo UUID da sua empresa
-- Substitua <codigo_ibge> pelo código do município

UPDATE empresas 
SET municipio_codigo = '3106200',  -- Exemplo: Belo Horizonte
    municipio_nome = 'Belo Horizonte'
WHERE id = '<empresa_id>';
```

**Códigos IBGE comuns:**
- Belo Horizonte/MG: `3106200`
- São Paulo/SP: `3550308`
- Rio de Janeiro/RJ: `3304557`
- Curitiba/PR: `4106902`
- Porto Alegre/RS: `4314902`

**Para encontrar o código do seu município:**
- https://www.ibge.gov.br/explica/codigos-dos-municipios.php
- Busque por "código IBGE [nome do município]"

---

## 🔐 Passo 2: Cadastrar Credenciais NFS-e

Você precisa obter credenciais da prefeitura do município da empresa:

### Opção A: Via API (Recomendado)

```bash
POST /api/v1/nfse/empresas/{empresa_id}/credenciais
Authorization: Bearer {seu_token_jwt}
Content-Type: application/json

{
  "municipio_codigo": "3106200",
  "usuario": "seu_usuario_prefeitura",
  "senha": "sua_senha_prefeitura",
  "cnpj": "18039919000154"  // Opcional
}
```

### Opção B: Via SQL Direto

```sql
INSERT INTO credenciais_nfse (
    empresa_id,
    municipio_codigo,
    usuario,
    senha,
    ativo
) VALUES (
    '<empresa_id>',
    '3106200',
    'seu_usuario',
    'sua_senha',
    true
);
```

**Como obter credenciais:**
1. Acesse o portal NFS-e do seu município
2. Cadastre-se como prestador de serviços
3. Gere login/senha para acesso à API
4. Use essas credenciais aqui

---

## 🧪 Passo 3: Testar Configuração

### Opção A: Script Python (Recomendado)

```bash
# Teste básico (só verifica configuração)
python scripts/test_nfse.py <empresa_id>

# Teste completo (também busca notas)
python scripts/test_nfse.py <empresa_id> --buscar-notas
```

### Opção B: Via API Endpoints

#### 3.1. Listar Municípios Suportados

```bash
GET /api/v1/nfse/municipios/suportados
Authorization: Bearer {token}
```

#### 3.2. Verificar Credenciais Cadastradas

```bash
GET /api/v1/nfse/empresas/{empresa_id}/credenciais
Authorization: Bearer {token}
```

#### 3.3. Testar Conexão (sem buscar notas)

```bash
POST /api/v1/nfse/empresas/{empresa_id}/testar-conexao
Authorization: Bearer {token}
```

**Resposta esperada:**
```json
{
  "success": true,
  "status": "conectado",
  "sistema": "Belo Horizonte",
  "mensagem": "Autenticação bem-sucedida no Belo Horizonte"
}
```

---

## 🔍 Passo 4: Buscar NFS-e

### Via API

```bash
POST /api/v1/nfse/empresas/{empresa_id}/buscar
Authorization: Bearer {token}
Content-Type: application/json

{
  "data_inicio": "2026-01-01",
  "data_fim": "2026-02-09"
}
```

**Sem parâmetros (usa últimos 30 dias):**
```bash
POST /api/v1/nfse/empresas/{empresa_id}/buscar
Authorization: Bearer {token}
Content-Type: application/json

{}
```

**Resposta esperada:**
```json
{
  "success": true,
  "notas": [
    {
      "id": "uuid",
      "numero_nf": "12345",
      "serie": "1",
      "data_emissao": "2026-02-01",
      "valor_total": 1500.00,
      "cnpj_emitente": "18039919000154",
      "nome_emitente": "EMPRESA TESTE LTDA",
      "descricao_servico": "Serviço de consultoria",
      "municipio_codigo": "3106200",
      "municipio_nome": "Belo Horizonte"
    }
  ],
  "quantidade": 1,
  "sistema": "Belo Horizonte",
  "tempo_ms": 1234
}
```

---

## 🐛 Troubleshooting

### Erro: "Empresa não tem municipio_codigo configurado"

**Solução:** Execute a migration `004_add_municipio_codigo_empresas.sql` e atualize a empresa:

```sql
UPDATE empresas 
SET municipio_codigo = '3106200' 
WHERE id = '<empresa_id>';
```

### Erro: "Credenciais NFS-e não configuradas"

**Solução:** Cadastre as credenciais usando o endpoint ou SQL acima.

### Erro: "Falha na autenticação"

**Possíveis causas:**
- Usuário/senha incorretos
- API municipal fora do ar
- Credenciais expiradas
- Município não suportado

**Solução:**
1. Verifique credenciais no portal da prefeitura
2. Teste login manual no portal
3. Verifique se o município está na lista suportada

### Erro: "Timeout ao conectar"

**Solução:**
- Verifique sua conexão com internet
- A API municipal pode estar temporariamente indisponível
- Tente novamente em alguns minutos

### Nenhuma nota encontrada

**Possíveis causas:**
- Não há NFS-e emitidas no período
- CNPJ da empresa não corresponde ao prestador
- Período muito curto

**Solução:**
- Aumente o período de busca
- Verifique se o CNPJ está correto
- Confirme no portal municipal se há notas emitidas

---

## ✅ Checklist de Teste

- [ ] Migration `003_nfse_credenciais_e_campos.sql` executada
- [ ] Migration `004_add_municipio_codigo_empresas.sql` executada
- [ ] Empresa tem `municipio_codigo` configurado
- [ ] Credenciais NFS-e cadastradas na tabela `credenciais_nfse`
- [ ] Endpoint `/municipios/suportados` retorna lista
- [ ] Endpoint `/empresas/{id}/credenciais` retorna credenciais
- [ ] Endpoint `/empresas/{id}/testar-conexao` retorna sucesso
- [ ] Endpoint `/empresas/{id}/buscar` retorna notas (ou lista vazia se não houver)

---

## 📞 Suporte

Se encontrar problemas:

1. Verifique os logs do servidor
2. Execute o script de teste: `python scripts/test_nfse.py <empresa_id>`
3. Verifique se as URLs das APIs municipais estão corretas (podem ter mudado)
4. Consulte a documentação oficial da API do seu município

---

## 🎯 Próximos Passos

Após testar com sucesso:

1. ✅ Integrar busca NFS-e no frontend
2. ✅ Criar job automático para busca periódica
3. ✅ Adicionar mais municípios conforme demanda
4. ✅ Implementar cache para reduzir chamadas à API
