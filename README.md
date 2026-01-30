# Hi-Control Backend API

API REST em Python/FastAPI para o sistema de gestão contábil Hi-Control.

## 🚀 Tecnologias

- **FastAPI** - Framework web assíncrono moderno
- **SQLAlchemy** - ORM para Python
- **Alembic** - Migrações de banco de dados
- **Pydantic** - Validação de dados
- **JWT** - Autenticação com JSON Web Tokens
- **SQLite** - Banco de dados (desenvolvimento)

## 📋 Pré-requisitos

- Python 3.10+
- pip (gerenciador de pacotes Python)

## 🔧 Instalação

### 1. Criar ambiente virtual

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Edite o arquivo `.env` e configure:
- `SECRET_KEY`: Gere uma chave segura com `openssl rand -hex 32`
- Outras variáveis conforme necessário

### 4. Inicializar banco de dados

```bash
# Criar migration inicial
alembic revision --autogenerate -m "Initial migration"

# Aplicar migrations
alembic upgrade head
```

### 5. Popular banco com dados de teste

```python
# Execute o script Python
python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from app.db.init_db import init_db
from app.db.base import Base
from app.db.session import engine

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        await init_db(session)

    print('✅ Banco de dados inicializado com sucesso!')

asyncio.run(main())
"
```

## 🏃 Executar

### Modo desenvolvimento (com hot reload)

```bash
uvicorn app.main:app --reload --port 8000
```

### Modo produção

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 📚 Documentação da API

Após iniciar o servidor, acesse:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json

## 🔐 Autenticação

### Credenciais de Teste

| Email | Senha | Plano |
|-------|-------|-------|
| admin@hicontrol.com | admin123 | Premium |
| premium@hicontrol.com | premium123 | Premium |
| basico@hicontrol.com | basico123 | Básico |

### Obter Token de Acesso

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@hicontrol.com&password=admin123"
```

Resposta:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

### Usar Token em Requisições

```bash
curl -X GET "http://localhost:8000/api/v1/notas" \
  -H "Authorization: Bearer {seu_access_token}"
```

## 🛣️ Rotas Principais

### Autenticação (`/api/v1/auth`)

- `POST /login` - Login com email e senha
- `POST /logout` - Logout (invalidar token)
- `GET /me` - Dados do usuário autenticado

### Notas Fiscais (`/api/v1/notas`)

- `GET /` - Buscar notas com filtros
  - Query params:
    - `search_term`: Busca geral
    - `tipo_nf`: NFE, NFCE, NFSE, CTE
    - `situacao`: Autorizada, Cancelada, etc
    - `data_inicio`, `data_fim`: Filtro por período
    - `skip`, `limit`: Paginação

### Exemplos de Uso

**Buscar todas as notas:**
```bash
curl -X GET "http://localhost:8000/api/v1/notas" \
  -H "Authorization: Bearer {token}"
```

**Buscar NF-e autorizadas:**
```bash
curl -X GET "http://localhost:8000/api/v1/notas?tipo_nf=NFE&situacao=Autorizada" \
  -H "Authorization: Bearer {token}"
```

**Buscar por termo:**
```bash
curl -X GET "http://localhost:8000/api/v1/notas?search_term=Tech" \
  -H "Authorization: Bearer {token}"
```

## 📁 Estrutura de Diretórios

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/       # Rotas da API
│   │       │   ├── auth.py
│   │       │   └── notas.py
│   │       └── router.py
│   ├── core/                    # Configurações e segurança
│   │   ├── config.py
│   │   └── security.py
│   ├── db/                      # Banco de dados
│   │   ├── base.py
│   │   ├── session.py
│   │   └── init_db.py
│   ├── models/                  # Modelos SQLAlchemy
│   │   ├── user.py
│   │   └── nota_fiscal.py
│   ├── schemas/                 # Schemas Pydantic
│   │   ├── auth.py
│   │   ├── user.py
│   │   └── nota_fiscal.py
│   ├── services/                # Lógica de negócio
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   └── nota_service.py
│   ├── main.py                  # Entry point
│   └── dependencies.py          # Dependências compartilhadas
├── alembic/                     # Migrações
├── tests/                       # Testes
├── requirements.txt
└── .env
```

## 🧪 Testes

```bash
# Instalar dependências de desenvolvimento
pip install -r requirements-dev.txt

# Executar testes
pytest tests/ -v

# Com cobertura
pytest tests/ -v --cov=app --cov-report=html
```

## 🔄 Migrações do Banco de Dados

### Criar nova migration

```bash
alembic revision --autogenerate -m "Descrição da mudança"
```

### Aplicar migrations

```bash
alembic upgrade head
```

### Reverter última migration

```bash
alembic downgrade -1
```

### Ver histórico

```bash
alembic history
```

## 🔒 Segurança

### Boas Práticas Implementadas

- ✅ Senhas hasheadas com bcrypt
- ✅ Autenticação JWT com tokens de curta duração
- ✅ CORS configurado para domínios específicos
- ✅ Validações rigorosas de dados fiscais (CNPJ, Chave de Acesso)
- ✅ Type hints em todo o código

### Melhorias Futuras

- [ ] Rate limiting (limitação de requisições)
- [ ] Blacklist de tokens (logout real)
- [ ] Auditoria de acesso
- [ ] HTTPS obrigatório em produção
- [ ] Certificado digital para assinatura de XMLs

## 📊 Validações Implementadas

### CNPJ
- Formato: `XX.XXX.XXX/XXXX-XX`
- Validação de estrutura com regex

### Chave de Acesso NF-e
- Exatamente 44 dígitos numéricos
- Sem formatação (apenas números)

### Valores Monetários
- Tipo `Decimal` (precisão fiscal)
- Máximo 2 casas decimais
- Não-negativos

## 🚀 Deploy em Produção

### Preparação

1. Alterar `DATABASE_URL` para PostgreSQL
2. Gerar `SECRET_KEY` segura
3. Configurar CORS para domínios específicos
4. Desabilitar `DEBUG=False`

### Docker (opcional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Variáveis de Ambiente de Produção

```env
SECRET_KEY=<chave_gerada_com_openssl>
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/hicontrol
DEBUG=False
CORS_ORIGINS=https://hi-control.vercel.app
ALLOWED_HOSTS=api.hicontrol.com
```

## 🆘 Troubleshooting

### Erro: "No module named 'app'"

Execute sempre do diretório `backend/`:
```bash
cd backend
python -m uvicorn app.main:app --reload
```

### Erro: "SECRET_KEY not found"

Certifique-se de ter um arquivo `.env` com `SECRET_KEY` configurada.

### Erro de conexão com banco de dados

Verifique se as migrations foram aplicadas:
```bash
alembic upgrade head
```

## 📞 Suporte

Para dúvidas ou problemas:
1. Consulte a documentação da API em `/api/docs`
2. Verifique os logs do servidor
3. Abra uma issue no repositório

## 📝 Licença

Este projeto é parte do sistema Hi-Control - Todos os direitos reservados.

---

**Desenvolvido com ❤️ para escritórios de contabilidade brasileiros**
