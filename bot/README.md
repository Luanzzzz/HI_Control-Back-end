# 🤖 Bot de Busca Automática de Notas Fiscais

Bot standalone para busca automática de NFS-e via Base Nacional (ABRASF) e APIs municipais.

## 🎯 Funcionalidades

- ✅ Busca NFS-e via Base Nacional (ABRASF) - 3.000+ municípios
- ✅ Usa credenciais das empresas cadastradas no Supabase
- ✅ Execução automática via APScheduler (configurável)
- ✅ Salva notas no Supabase com zero duplicidade (UPSERT)
- ✅ Logging detalhado e error handling robusto
- ✅ Seguindo padrões MCP (Model Context Protocol)

## 📋 Pré-requisitos

- Python 3.10+
- Conta Supabase configurada
- Credenciais NFS-e cadastradas no sistema

## 🚀 Instalação

```bash
# 1. Instalar dependências
cd bot/
pip install -r requirements.txt

# 2. Configurar variáveis de ambiente
cp ../.env.example .env
# Editar .env com suas credenciais
```

## ⚙️ Configuração

Ver `BOT_IMPLEMENTADO.md` para lista completa de variáveis de ambiente.

Variáveis obrigatórias:
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`

## 🏃 Execução

```bash
# Execução manual
python bot/main.py

# Execução em background
nohup python bot/main.py > bot_output.log 2>&1 &
```

## 📊 Logs

Logs são salvos em `bot/logs/bot.log` e também exibidos no console.

## 🔍 Estrutura

```
bot/
├── main.py              # Script principal
├── config.py            # Configurações
├── adapters/            # Adapters NFS-e
│   └── base_nacional.py
└── utils/               # Utilitários
    ├── supabase_client.py
    └── certificado.py
```

## 📚 Documentação

Ver `BOT_IMPLEMENTADO.md` para documentação completa.
