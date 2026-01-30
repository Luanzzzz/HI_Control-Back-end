# 📚 Guia de Uso da API - Busca de Notas Fiscais

## 🔐 Autenticação

Todos os endpoints de notas fiscais requerem autenticação via JWT token.

### 1. Fazer Login

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=teste@hicontrol.com.br&password=HiControl@2024"
```

**Resposta:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Salve o `access_token` para usar nas próximas requisições.

---

## 📝 Endpoints de Busca de Notas Fiscais

### 2. Busca Geral de Notas (GET /api/v1/notas)

Busca flexível com filtros opcionais e paginação.

**Exemplo 1: Buscar todas as notas (primeiras 100)**

```bash
curl -X GET "http://localhost:8000/api/v1/notas" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 2: Buscar por termo (busca em número, chave, CNPJ, nome)**

```bash
curl -X GET "http://localhost:8000/api/v1/notas?search_term=Tech" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 3: Filtrar por tipo e situação**

```bash
curl -X GET "http://localhost:8000/api/v1/notas?tipo_nf=NFe&situacao=autorizada" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 4: Buscar por período**

```bash
curl -X GET "http://localhost:8000/api/v1/notas?data_inicio=2024-01-01T00:00:00&data_fim=2024-01-31T23:59:59" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 5: Buscar por CNPJ emitente**

```bash
curl -X GET "http://localhost:8000/api/v1/notas?cnpj_emitente=12.345.678/0001-90" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 6: Paginação (pular 50, trazer 25)**

```bash
curl -X GET "http://localhost:8000/api/v1/notas?skip=50&limit=25" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 7: Combinando filtros**

```bash
curl -X GET "http://localhost:8000/api/v1/notas?tipo_nf=NFe&situacao=autorizada&search_term=Tech&limit=10" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

---

### 3. Busca Avançada de Notas (GET /api/v1/notas/buscar)

Busca com filtros específicos e obrigatórios (período).

**Exemplo 1: Buscar notas do último mês**

```bash
curl -X GET "http://localhost:8000/api/v1/notas/buscar?data_inicio=2024-01-01&data_fim=2024-01-31" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 2: Buscar NF-e autorizadas**

```bash
curl -X GET "http://localhost:8000/api/v1/notas/buscar?data_inicio=2024-01-01&data_fim=2024-01-31&tipo_nf=NFe&situacao=autorizada" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 3: Buscar por número e série específicos**

```bash
curl -X GET "http://localhost:8000/api/v1/notas/buscar?data_inicio=2024-01-01&data_fim=2024-01-31&numero_nf=000000123&serie=1" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Exemplo 4: Buscar notas de um emitente específico**

```bash
curl -X GET "http://localhost:8000/api/v1/notas/buscar?data_inicio=2024-01-01&data_fim=2024-01-31&cnpj_emitente=12.345.678/0001-90" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

---

### 4. Obter Detalhes de uma Nota (GET /api/v1/notas/{chave_acesso})

Retorna detalhes completos incluindo impostos.

**Exemplo:**

```bash
curl -X GET "http://localhost:8000/api/v1/notas/35240112345678000190550010000001231000000001" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Resposta (exemplo):**
```json
{
  "id": "uuid-123",
  "empresa_id": "uuid-empresa",
  "numero_nf": "000000123",
  "serie": "1",
  "tipo_nf": "NFe",
  "modelo": "55",
  "chave_acesso": "35240112345678000190550010000001231000000001",
  "data_emissao": "2024-01-20T10:30:00",
  "data_autorizacao": "2024-01-20T10:45:00",
  "valor_total": 5400.00,
  "valor_produtos": 5000.00,
  "valor_servicos": null,
  "cnpj_emitente": "12.345.678/0001-90",
  "nome_emitente": "Tech Solutions Ltda",
  "cnpj_destinatario": "98.765.432/0001-11",
  "nome_destinatario": "Cliente ABC Comércio",
  "situacao": "autorizada",
  "protocolo": "135240000123456",
  "xml_url": null,
  "pdf_url": null,
  "observacoes": "Nota fiscal de venda de equipamentos",
  "valor_icms": 648.00,
  "valor_ipi": 162.00,
  "valor_pis": 89.10,
  "valor_cofins": 410.40,
  "motivo_cancelamento": null,
  "tags": ["venda", "produto"],
  "created_at": "2024-01-20T10:30:00",
  "updated_at": "2024-01-20T10:30:00",
  "deleted_at": null
}
```

---

### 5. Baixar XML da Nota (GET /api/v1/notas/{chave_acesso}/xml)

Faz download do arquivo XML da nota fiscal.

**Exemplo (curl salva em arquivo):**

```bash
curl -X GET "http://localhost:8000/api/v1/notas/35240112345678000190550010000001231000000001/xml" \
  -H "Authorization: Bearer {seu_token_aqui}" \
  -o nota_fiscal.xml
```

**Exemplo (wget):**

```bash
wget --header="Authorization: Bearer {seu_token_aqui}" \
  "http://localhost:8000/api/v1/notas/35240112345678000190550010000001231000000001/xml" \
  -O nota_fiscal.xml
```

---

### 6. Estatísticas de Notas (GET /api/v1/notas/estatisticas/resumo)

Retorna estatísticas resumidas do período.

**Exemplo:**

```bash
curl -X GET "http://localhost:8000/api/v1/notas/estatisticas/resumo?data_inicio=2024-01-01&data_fim=2024-01-31" \
  -H "Authorization: Bearer {seu_token_aqui}"
```

**Resposta (exemplo):**
```json
{
  "periodo": {
    "data_inicio": "2024-01-01",
    "data_fim": "2024-01-31"
  },
  "resumo": {
    "total_notas": 10,
    "valor_total": 54850.50,
    "valor_medio": 5485.05
  },
  "por_tipo": {
    "NFe": 6,
    "NFCe": 2,
    "NFSe": 2,
    "CTe": 0
  },
  "por_situacao": {
    "autorizada": 7,
    "cancelada": 1,
    "processando": 1,
    "denegada": 1
  }
}
```

---

## 🧪 Testes com Python (requests)

```python
import requests

# 1. Login
login_response = requests.post(
    "http://localhost:8000/api/v1/auth/login",
    data={
        "username": "teste@hicontrol.com.br",
        "password": "HiControl@2024"
    }
)
token = login_response.json()["access_token"]

# 2. Buscar notas
headers = {"Authorization": f"Bearer {token}"}

notas_response = requests.get(
    "http://localhost:8000/api/v1/notas",
    headers=headers,
    params={
        "tipo_nf": "NFe",
        "situacao": "autorizada",
        "limit": 10
    }
)

notas = notas_response.json()
print(f"Encontradas {len(notas)} notas")

# 3. Obter detalhes de uma nota
if notas:
    chave = notas[0]["chave_acesso"]
    detalhes = requests.get(
        f"http://localhost:8000/api/v1/notas/{chave}",
        headers=headers
    )
    print(detalhes.json())

# 4. Baixar XML
xml_response = requests.get(
    f"http://localhost:8000/api/v1/notas/{chave}/xml",
    headers=headers
)
with open("nota.xml", "wb") as f:
    f.write(xml_response.content)
```

---

## 🧪 Testes com JavaScript (fetch)

```javascript
// 1. Login
const loginResponse = await fetch('http://localhost:8000/api/v1/auth/login', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/x-www-form-urlencoded',
  },
  body: 'username=teste@hicontrol.com.br&password=HiControl@2024'
});

const { access_token } = await loginResponse.json();

// 2. Buscar notas
const notasResponse = await fetch(
  'http://localhost:8000/api/v1/notas?tipo_nf=NFe&limit=10',
  {
    headers: {
      'Authorization': `Bearer ${access_token}`
    }
  }
);

const notas = await notasResponse.json();
console.log(`Encontradas ${notas.length} notas`);

// 3. Obter detalhes
const chave = notas[0].chave_acesso;
const detalhesResponse = await fetch(
  `http://localhost:8000/api/v1/notas/${chave}`,
  {
    headers: {
      'Authorization': `Bearer ${access_token}`
    }
  }
);

const detalhes = await detalhesResponse.json();
console.log(detalhes);

// 4. Baixar XML
const xmlResponse = await fetch(
  `http://localhost:8000/api/v1/notas/${chave}/xml`,
  {
    headers: {
      'Authorization': `Bearer ${access_token}`
    }
  }
);

const xmlBlob = await xmlResponse.blob();
// Criar link para download
const url = window.URL.createObjectURL(xmlBlob);
const a = document.createElement('a');
a.href = url;
a.download = `NFe${chave}.xml`;
a.click();
```

---

## ⚠️ Tratamento de Erros

### Erro 401 - Não Autenticado

```json
{
  "detail": "Não foi possível validar as credenciais"
}
```

**Solução:** Faça login novamente e use um token válido.

### Erro 403 - Módulo não incluído no plano

```json
{
  "detail": "Seu plano não inclui o módulo 'buscador_notas'. Faça upgrade para acessar."
}
```

**Solução:** Upgrade do plano necessário.

### Erro 400 - Parâmetros inválidos

```json
{
  "detail": "Período de busca não pode exceder 90 dias (período atual: 120 dias)"
}
```

**Solução:** Ajuste os parâmetros conforme a mensagem de erro.

### Erro 404 - Nota não encontrada

```json
{
  "detail": "Nota fiscal com chave 35240112345... não encontrada"
}
```

**Solução:** Verifique se a chave está correta e se a nota existe.

### Erro 422 - Validação falhou

```json
{
  "detail": "Chave de acesso inválida. Deve conter 44 dígitos numéricos válidos."
}
```

**Solução:** Corrija os dados enviados conforme validações fiscais.

---

## 📊 Validações Fiscais Implementadas

### CNPJ
- Formato: `XX.XXX.XXX/XXXX-XX`
- Validação de dígitos verificadores
- Apenas números permitidos na base

### Chave de Acesso NF-e
- Exatamente 44 dígitos numéricos
- Validação de dígito verificador (módulo 11)
- Validação de UF e modelo
- Estrutura: UF(2) + AAMM(6) + CNPJ(14) + MOD(2) + SERIE(3) + NUM(9) + COD(7) + DV(1)

### Período de Busca
- Máximo 90 dias entre data_inicio e data_fim
- Datas não podem ser futuras
- Máximo 5 anos no passado

---

## 🚀 Próximos Passos (TODO)

- [ ] Substituir mock por integração real com Supabase
- [ ] Implementar download de XML do Supabase Storage
- [ ] Integrar com biblioteca `python-nfe` para consulta SEFAZ
- [ ] Adicionar upload de XMLs
- [ ] Implementar validação de assinatura digital
- [ ] Adicionar filtros por empresa_id
- [ ] Implementar cache de consultas frequentes

---

**Desenvolvido para Hi-Control - Sistema de Gestão Contábil** 🎯
