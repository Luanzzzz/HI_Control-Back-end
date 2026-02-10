# ✅ BOT DE BUSCA ESTRUTURADO

**Data:** 10/02/2026  
**Status:** 🏗️ ESTRUTURA COMPLETA – AGUARDANDO CONFIGURAÇÃO (CREDENCIAIS NFS-E E OPCIONAL DRIVE)

---

## Estrutura atual do bot

```
bot/
├── __init__.py
├── config.py              # Configurações (Supabase, intervalo, dias retroativos, log)
├── main.py                # Bot principal + APScheduler
├── requirements.txt
├── .env.example
├── README.md
├── adapters/
│   ├── __init__.py
│   └── base_nacional.py   # Adapter Sistema Nacional NFS-e (ABRASF)
└── utils/
    ├── __init__.py
    ├── certificado.py     # Carregamento de certificado A1 (se necessário)
    └── supabase_client.py # SupabaseResource (empresas, notas, credenciais NFS-e)
```

**Observação:** O bot **não** possui `utils/google_drive_client.py`. O envio de XMLs para o Drive é feito pelo **backend** via `app.services.google_drive_service` (quando o bot roda no mesmo processo/ambiente e o serviço está disponível).

---

## Status dos componentes

### ✅ Funcionando

- **Bot principal** (`main.py`): orquestra busca, salva no Supabase, opcionalmente envia XMLs ao Drive.
- **SupabaseResource** (`utils/supabase_client.py`): empresas **ativas** (coluna `ativa`), credenciais NFS-e, upsert de notas (schema com `numero_nf`, `tipo_nf`, `cnpj_emitente`, etc.).
- **BaseNacionalAdapter** (`adapters/base_nacional.py`): integração com Sistema Nacional (URL produção/homologação), autenticação e busca de notas.
- **Config** (`config.py`): validação de variáveis (Supabase obrigatório), intervalo e dias retroativos.
- **APScheduler**: execução periódica e opção de execução imediata.

### ⚠️ Depende de configuração

- **Credenciais NFS-e por empresa**: tabela de credenciais (usuário/senha) por empresa e município; o bot usa `SupabaseResource.buscar_credenciais_nfse(empresa_id, municipio_codigo)`.
- **Google Drive (opcional)**:
  - Backend: endpoints em `app/api/v1/endpoints/drive_import_endpoints.py` retornam **503** com `error: "google_not_configured"` quando `GOOGLE_CLIENT_ID` ou `GOOGLE_REDIRECT_URI` não estão configurados.
  - Se o Drive estiver configurado no backend, o bot usa `google_drive_service.salvar_xml_no_drive` para salvar XMLs.

---

## Ajustes feitos (correção emergencial)

1. **Google Drive**
   - Endpoints que dependem do Google (`/auth/url`, `/auth/callback`, `/pastas/{config_id}`, `/sincronizar/{config_id}`) chamam `_exigir_google_configurado()` e retornam **503** com corpo estruturado quando OAuth não está configurado.
   - Em `app/core/config.py`, ao carregar settings, é emitido um **warning** se Google não estiver configurado (não bloqueia o startup).
   - `.env.example` atualizado com **placeholders** para Google (sem credenciais reais) e comentário para desenvolvimento local.

2. **Schema e bot**
   - Uso de **`ativa`** (não `ativo`) na tabela `empresas` já está aplicado no bot e nos endpoints do backend.

---

## Como fazer o bot buscar notas de verdade

### 1. Credenciais NFS-e por empresa

- Garantir que cada empresa tenha **credenciais NFS-e** (usuário/senha do sistema municipal/nacional) associadas ao **município** da empresa.
- O bot chama `SupabaseResource.buscar_credenciais_nfse(empresa_id, municipio_codigo)`; se não houver registro, a empresa é ignorada na busca.

### 2. Base Nacional (Sistema Nacional)

- O adapter usa as URLs oficiais (produção/homologação) do Sistema Nacional.
- Manter `bot/config.py` com `BASE_NACIONAL_HOMOLOGACAO` conforme o ambiente desejado.

### 3. Google Drive (opcional)

- Configurar no **backend** `GOOGLE_CLIENT_ID` e `GOOGLE_REDIRECT_URI` (e `GOOGLE_CLIENT_SECRET` onde necessário) no `.env`.
- Fluxo de autorização OAuth via endpoints `/drive/auth/url` e `/drive/auth/callback`.
- Com isso, o bot poderá usar `google_drive_service.salvar_xml_no_drive` quando estiver rodando no mesmo contexto do backend.

### 4. Executar o bot

```bash
cd HI_Control-Back-end
# Garantir .env (ou bot/.env) com SUPABASE_URL, SUPABASE_SERVICE_KEY, etc.
pip install -r bot/requirements.txt  # se necessário
python -m bot.main
```

---

## Troubleshooting

- **"column empresas.ativo does not exist"**  
  O schema usa **`ativa`**. Não crie coluna `ativo`; o código já foi ajustado para `ativa`.

- **"Google OAuth não configurado" (503)**  
  Configure `GOOGLE_CLIENT_ID` e `GOOGLE_REDIRECT_URI` no `.env` do backend. Para apenas testar o bot sem Drive, pode deixar sem Google; o bot continuará salvando notas no Supabase.

- **Bot não encontra empresas**  
  Verifique no Supabase: `empresas` com `ativa = true` e, para busca NFS-e, credenciais cadastradas para o `municipio_codigo` da empresa.

- **Nenhuma nota retornada**  
  Confirme credenciais NFS-e (usuário/senha) e período (dias retroativos em `config.DIAS_RETROATIVOS`). Verifique logs do bot e do adapter (autenticação e resposta da API).

---

## Próximos passos sugeridos

1. Garantir credenciais NFS-e por empresa/município no banco.
2. Configurar Google OAuth no backend se quiser XMLs no Drive.
3. Rodar o bot em ambiente de homologação/produção (cron ou processo gerenciado).
4. Validar no frontend a listagem de notas por empresa (endpoint de notas já existente).

**BOT PRONTO PARA CONFIGURAÇÃO E USO COM DADOS REAIS.**
