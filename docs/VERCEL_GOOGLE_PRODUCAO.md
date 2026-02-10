# Google Drive em produção (Vercel)

Para o backend na Vercel usar as credenciais do Google e você testar de verdade em produção, siga estes passos.

---

## 1. Variáveis de ambiente na Vercel

As credenciais que você já cadastrou no `.env.example` precisam estar **também** nas variáveis de ambiente do projeto na Vercel.

### Onde configurar

1. Acesse [Vercel Dashboard](https://vercel.com/dashboard).
2. Abra o projeto do **backend** (ex.: `HI_Control-Back-end` ou o nome que estiver na URL `backend-gamma-cyan-75.vercel.app`).
3. Vá em **Settings** → **Environment Variables**.

### Variáveis a adicionar (Produção)

Copie **nome** e **valor** do seu `.env.example` (ou do `.env` local) para cada variável abaixo.  
Marque o ambiente **Production** (e **Preview** se quiser testar em deploy de branch).

**Atalho:** na raiz do backend, rode:
```bash
python scripts/copiar_google_para_vercel.py
```
Isso gera o arquivo `vercel_env_google.txt` (ignorado pelo Git) com as três variáveis e valores. Abra o arquivo e use para colar na Vercel.  
(O script lê primeiro `.env.example` e depois `.env`; se o `.env` tiver as mesmas chaves, ele sobrescreve. Para usar só as credenciais do `.env.example`, rode o script com o `.env.example` já preenchido.)

| Nome                     | Valor (copie do .env.example) | Ambiente   |
|--------------------------|-------------------------------|------------|
| `GOOGLE_CLIENT_ID`       | (valor da linha GOOGLE_CLIENT_ID) | Production |
| `GOOGLE_CLIENT_SECRET`   | (valor da linha GOOGLE_CLIENT_SECRET) | Production |
| `GOOGLE_REDIRECT_URI`    | `https://backend-gamma-cyan-75.vercel.app/api/v1/drive/callback` | Production |

- **GOOGLE_REDIRECT_URI** em produção deve ser exatamente a URL do seu backend na Vercel (como acima). Se a URL do projeto for outra, use essa outra URL + `/api/v1/drive/callback`.

Depois de salvar, faça um **redeploy** do projeto (Deployments → ⋮ no último deploy → Redeploy) para as variáveis passarem a valer.

---

## 2. Google Cloud Console (URI de redirecionamento)

Para o OAuth do Google aceitar o callback em produção:

1. Acesse [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2. Abra as credenciais OAuth 2.0 do tipo **Aplicativo Web** que você usa no Hi-Control.
3. Em **URIs de redirecionamento autorizados**, confira se existe:
   - `https://backend-gamma-cyan-75.vercel.app/api/v1/drive/callback`
4. Se não existir, clique em **+ ADICIONAR URI**, cole essa URL e salve.

Assim o fluxo de “Login com Google” e salvamento de XMLs no Drive funcionam em produção.

---

## 3. Conferir se está funcionando

1. Redeploy do backend na Vercel (após salvar as env vars).
2. No frontend em produção (ou apontando para o backend na Vercel), use a função de **conectar Google Drive** ou **autorizar Drive**.
3. Você deve ser redirecionado para o Google, autorizar e voltar para o app sem erro 503.
4. Se aparecer 503, confira:
   - Se as três variáveis estão em **Production** (e se fez redeploy).
   - Se a URI de redirecionamento no Google Cloud está exatamente igual à do backend (incluindo `https://` e `/api/v1/drive/callback`).

---

## Resumo

- Credenciais em **produção** vêm das **Environment Variables** da Vercel, não do `.env.example`.
- Copie `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` e `GOOGLE_REDIRECT_URI` do seu `.env.example` (ou `.env`) para o projeto do backend na Vercel, ambiente **Production**.
- Mantenha no Google Cloud a URI de redirecionamento da URL real do backend na Vercel.
- Depois disso, você pode testar de verdade o sistema de produção na Vercel com Google Drive.
