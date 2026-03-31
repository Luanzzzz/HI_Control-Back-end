# Hi-Control Backend API

API REST em Python/FastAPI para o sistema de gestão contábil Hi-Control — plataforma para escritórios de contabilidade brasileiros.

## Tecnologias

- **Python 3.12** — Linguagem principal
- **FastAPI** — Framework web assíncrono
- **Supabase (PostgreSQL)** — Banco de dados com Row Level Security
- **Pydantic v2** — Validação de dados
- **JWT (python-jose)** — Autenticação via tokens
- **bcrypt** — Hash de senhas
- **lxml** — Parsing de XMLs NF-e
- **cryptography (PKCS12)** — Certificados digitais A1

## Pré-requisitos

- Python 3.12+
- Conta Supabase configurada

## Instalação

```bash
cd backend
python -m venv venv
venv\Scripts\activate   # Windows
# ou
source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
```

## Configuração

Crie um arquivo `.env` em `backend/` com:

```env
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...        # anon key
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # service_role key
SECRET_KEY=<gere com: openssl rand -hex 32>

# Opcional - certificado A1 para comunicação SEFAZ
CERTIFICATE_A1_FILE=path/to/certificado.pfx
CERTIFICATE_PASSWORD=senha_do_certificado
CERTIFICATE_ENCRYPTION_KEY=<chave Fernet para criptografar cert no banco>

# Opcional - nunca usar true em produção
USE_MOCK_SEFAZ=false
```

## Executar

```bash
# Desenvolvimento (hot reload)
uvicorn app.main:app --reload --port 8000

# Produção
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Documentação Interativa

- **Swagger UI:** http://localhost:8000/api/v1/docs
- **ReDoc:** http://localhost:8000/api/v1/redoc

---

## Mapeamento de Funcionalidades

### Autenticação (`/api/v1/auth`)

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| POST | `/auth/login` | Login — retorna access_token e refresh_token |
| POST | `/auth/logout` | Logout do usuário |
| GET | `/auth/me` | Dados do usuário autenticado |

Autenticação usa JWT com:
- **Access token:** expiração configurável (padrão 30min)
- **Refresh token:** expiração longa (padrão 7 dias)
- **bcrypt** para hash de senhas

### Certificados Digitais (`/api/v1/certificados`)

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| POST | `/certificados/empresas/{id}/certificado` | Upload de certificado A1 (.pfx) |
| GET | `/certificados/empresas/{id}/certificado/status` | Status/validade do certificado |

O sistema suporta estratégia híbrida: tenta o certificado da empresa, se não existir usa o do contador.
Certificados são armazenados criptografados com Fernet (ou base64 se sem chave configurada).

### Busca e Importação de Notas Fiscais (`/api/v1/nfe`)

#### Busca no banco de dados local

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| POST | `/nfe/buscar` | Busca notas com filtros (CNPJ, período, tipo, situação) |
| POST | `/nfe/buscar/iniciar` | Inicia busca assíncrona em background |
| GET | `/nfe/buscar/stats/{cnpj}` | Estatísticas de busca por CNPJ |
| GET | `/nfe/buscar/status/{job_id}` | Status de busca assíncrona |
| GET | `/nfe/empresas/{id}/notas` | Lista notas da empresa (paginado) |
| POST | `/nfe/empresas/{id}/notas/buscar` | Busca avançada com filtros |
| GET | `/nfe/empresas/{id}/notas/historico` | Histórico de consultas |

#### Importação de XML

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| POST | `/nfe/importar-xml` | Importar XML individual de NF-e ou NFC-e |
| POST | `/nfe/importar-lote` | Importar lote de XMLs via arquivo ZIP (máx 100 XMLs, 50MB) |

**Para obter XMLs:** Use o Portal Nacional NF-e (https://www.nfe.fazenda.gov.br) e importe via esses endpoints.

#### Download de XML

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| GET | `/nfe/notas/{chave_acesso}/xml` | Download XML da nota pelo hash de 44 dígitos |

#### Consulta SEFAZ

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| GET | `/nfe/consultar-chave/{chave_acesso}` | Consulta status da nota no SEFAZ (requer certificado) |
| GET | `/nfe/empresas/{id}/certificado/status` | Status do certificado da empresa |

### Emissão de NF-e (`/api/v1/nfe`)

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| POST | `/nfe/autorizar` | Autorizar NF-e junto à SEFAZ |
| POST | `/nfe/consultar/{chave}` | Consultar protocolo da NF-e |
| POST | `/nfe/cancelar/{chave}` | Cancelar NF-e (dentro de 24h) |

**Nota:** Requer PyNFE e OpenSSL compatível. Atualmente indisponível por incompatibilidade com OpenSSL recente.

### Notas Fiscais — Leitura Rápida (`/api/v1/notas`)

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| GET | `/notas/buscar` | Busca notas com search_term, tipo_nf, situacao, período |
| GET | `/notas/` | Lista todas as notas da empresa |
| GET | `/notas/{chave}` | Detalhes de uma nota específica |
| GET | `/notas/{chave}/xml` | Download XML da nota |
| GET | `/notas/estatisticas/resumo` | Resumo estatístico (totais, valores, tipos) |

### Empresas (`/api/v1/empresas`)

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| GET | `/empresas` | Listar empresas do usuário |
| POST | `/empresas` | Criar nova empresa |
| GET | `/empresas/{id}` | Detalhes da empresa |
| PUT | `/empresas/{id}` | Atualizar empresa |
| DELETE | `/empresas/{id}` | Remover empresa |
| GET | `/empresas/check-cnpj/{cnpj}` | Verificar CNPJ disponível |

### Perfil do Usuário (`/api/v1/perfil`)

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| GET | `/perfil/` | Dados do perfil |
| PUT | `/perfil/` | Atualizar perfil |

### Perfil Contador (`/api/v1/perfil-contador`)

| Método | Endpoint | Descrição |
|--------|---------|-----------|
| GET | `/perfil-contador` | Dados do contador |
| PUT | `/perfil-contador` | Atualizar dados |
| POST | `/perfil-contador/logo` | Upload do logo |
| POST | `/perfil-contador/certificado` | Upload do certificado A1 |
| GET | `/perfil-contador/certificado/status` | Status do certificado |

---

## Arquitetura

### Estrutura de Diretórios

```
backend/
├── app/
│   ├── api/v1/
│   │   ├── endpoints/
│   │   │   ├── auth.py              # Autenticação JWT
│   │   │   ├── buscar_notas.py      # Busca, importação, download de NF-e
│   │   │   ├── certificados.py      # Gestão de certificados A1
│   │   │   ├── debug.py             # Diagnóstico (só fora de produção)
│   │   │   ├── emissao_nfe.py       # Emissão NF-e (PyNFE)
│   │   │   ├── empresas.py          # CRUD de empresas
│   │   │   ├── notas.py             # Leitura de notas (acesso rápido)
│   │   │   ├── perfil.py            # Perfil do usuário
│   │   │   └── perfil_contador.py   # Perfil do contador
│   │   └── router.py                # Agrega todos os routers
│   ├── adapters/
│   │   └── pynfe_adapter.py         # Adapter PyNFE (lazy loading)
│   ├── core/
│   │   ├── config.py                # Settings com Pydantic BaseSettings
│   │   ├── security.py              # JWT, bcrypt
│   │   └── sefaz_config.py          # URLs SEFAZ por UF, cache in-memory
│   ├── db/
│   │   └── supabase_client.py       # Clientes Supabase (anon + admin)
│   ├── models/
│   │   ├── nfe_busca.py             # NFeBuscadaMetadata, DistribuicaoResponseModel
│   │   ├── nfe_completa.py          # NotaFiscalCompletaCreate, SefazResponseModel
│   │   └── nota_fiscal.py           # NotaFiscalCreate, NotaFiscalResponse
│   ├── services/
│   │   ├── busca_nf_service.py      # Busca no banco local (real, sem mock)
│   │   ├── certificado_service.py   # Validação e criptografia de certificados
│   │   ├── nfe_mapper.py            # Mapeamento NFeBuscadaMetadata → NotaFiscalCreate
│   │   ├── plan_validation.py       # Limites por plano (Básico/Premium/Enterprise)
│   │   ├── real_consulta_service.py # Parsing de XML NF-e/NFC-e
│   │   └── sefaz_service.py         # Comunicação SEFAZ (autorização, consulta, cancelamento)
│   ├── utils/
│   │   └── validators.py            # validar_cnpj, validar_chave_nfe, validar_periodo
│   ├── dependencies.py              # Injeção de dependências FastAPI
│   └── main.py                      # Entry point, CORS, startup/shutdown
├── docs/
│   └── ERROS_E_CORRECOES.md         # Relatório de bugs e correções
├── tests/
│   ├── conftest.py                  # Fixtures globais + variáveis de ambiente mock
│   ├── integration/
│   │   └── test_pynfe_integration.py
│   └── unit/
│       ├── test_busca_nf_service.py
│       ├── test_certificado_service.py
│       ├── test_models.py
│       ├── test_nfe_mapper.py
│       ├── test_plan_validation.py
│       ├── test_real_consulta_service.py
│       ├── test_security.py
│       ├── test_sefaz_config.py
│       ├── test_sefaz_service.py
│       └── test_validators.py
├── pytest.ini
├── requirements.txt
└── requirements-dev.txt
```

### Fluxo de Dados — Notas Fiscais

```
Usuário → Importar XML → real_consulta_service.importar_xml()
                       → NotaFiscalCreate (Pydantic)
                       → Supabase (tabela notas_fiscais)

Usuário → Buscar notas → busca_nf_service.buscar_notas()
                       → Supabase (query com filtros)
                       → List[NotaFiscalResponse]

Usuário → Download XML → busca_nf_service.baixar_xml()
                       → Supabase (xml_completo ou xml_resumo)
                       → bytes (XML)
```

### Endpoints SEFAZ Configurados

Todos os 27 estados brasileiros em ambiente **homologação**:
- Consulta de NF-e por chave (`consulta`)
- Autorização (`autorizacao`)
- Cancelamento (`cancelamento`)
- Inutilização (`inutilizacao`)
- Status do serviço (`status_servico`)

**Não configurado:** DistribuicaoDFe (motivo: retorna erro 999 "Operação não suportada").

### Estrutura da Chave de Acesso NF-e (44 dígitos)

```
Posição  Conteúdo
[0:2]    Código UF (ex: 35 = SP)
[2:8]    AAMM — Ano e Mês de emissão (6 dígitos)
[8:22]   CNPJ do emitente (14 dígitos)
[22:24]  Modelo: 55=NF-e, 65=NFC-e, 57=CT-e
[24:27]  Série (3 dígitos)
[27:36]  Número da NF (9 dígitos)
[36:43]  Código numérico randômico (7 dígitos)
[43]     Dígito verificador módulo 11
```

---

## Testes

```bash
# Executar todos os testes
pytest tests/ -v

# Apenas testes unitários
pytest tests/unit/ -v

# Com relatório de cobertura
pytest tests/unit/ --cov=app --cov-report=html
```

**Resultado atual:** 224 passed, 6 skipped (PyNFE indisponível)

---

## Planos de Acesso

| Plano | Empresas | Notas/mês | Histórico |
|-------|---------|-----------|-----------|
| Básico | 1 | 100 | 30 dias |
| Premium | 5 | 1000 | 180 dias |
| Enterprise | Ilimitado | Ilimitado | 1825 dias |

**DEV MODE:** Em desenvolvimento, todos os limites são substituídos por Enterprise.

---

## Segurança

- Senhas hasheadas com bcrypt (salt automático)
- Tokens JWT com expiração curta (access) e longa (refresh)
- Certificados A1 armazenados criptografados com Fernet
- CORS configurado com lista de origens permitidas
- RLS bypass via Supabase service_role apenas no backend
- Validação completa de CNPJ (dígitos verificadores) e Chave NF-e (módulo 11)

---

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|----------|------------|-----------|
| `SUPABASE_URL` | Sim | URL do projeto Supabase |
| `SUPABASE_KEY` | Sim | Chave anon (acesso público) |
| `SUPABASE_SERVICE_KEY` | Sim | Chave service_role (bypass RLS) |
| `SECRET_KEY` | Sim | Chave para assinar JWT |
| `CERTIFICATE_A1_FILE` | Não | Caminho do .pfx padrão |
| `CERTIFICATE_PASSWORD` | Não | Senha do certificado .pfx |
| `CERTIFICATE_ENCRYPTION_KEY` | Não | Chave Fernet para criptografar cert no banco |
| `USE_MOCK_SEFAZ` | Não | `false` em produção (sempre) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Não | Default: 30 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Não | Default: 7 |

---

## Limitações Conhecidas

1. **Emissão NF-e indisponível** — PyNFE tem incompatibilidade com OpenSSL recente (`verify` removido). Importação de XML e consulta SEFAZ funcionam normalmente.

2. **CT-e sem importação XML** — `importar_xml()` rejeita arquivos CT-e. Suporte planejado para versão futura.

3. **Sem exportação Google Drive** — Funcionalidade não implementada. Para exportar XMLs, use o download individual ou lote ZIP.

4. **DistribuicaoDFe indisponível** — O WebService SEFAZ para distribuição automática não está habilitado. Use o Portal Nacional NF-e para download em lote.

---

Desenvolvido para escritórios de contabilidade brasileiros.
