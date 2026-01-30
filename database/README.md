# 🗄️ Banco de Dados Hi-Control - Supabase

## 📋 Configuração Inicial

### 1. Criar Projeto no Supabase

1. Acesse [supabase.com](https://supabase.com)
2. Crie uma nova organização e projeto
3. Aguarde provisioning (~2 minutos)
4. Copie as credenciais:
   - **URL**: Settings > API > Project URL
   - **Anon Key**: Settings > API > Project API keys > anon/public
   - **Service Role Key**: Settings > API > Project API keys > service_role

### 2. Executar Schema

1. Abra o SQL Editor no Supabase Dashboard
2. Cole o conteúdo completo de `schema.sql`
3. Execute o script (Run)
4. Verifique se todas as tabelas foram criadas

### 3. Configurar .env

Copie `.env.example` para `.env` e preencha:
```env
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_KEY=sua-anon-key-aqui
SUPABASE_SERVICE_KEY=sua-service-role-key-aqui
SECRET_KEY=sua-chave-secreta-jwt-aqui
```

## 🏗️ Estrutura de Tabelas

### Tabelas Principais

- **usuarios**: Cadastro de contadores/usuários
- **planos**: Definição dos planos (básico, profissional, enterprise)
- **assinaturas**: Assinaturas ativas dos usuários
- **empresas**: Empresas clientes dos contadores
- **notas_fiscais**: Registro de notas fiscais (MVP - Supabase)

### Relacionamentos
```
usuarios (1) -----> (N) assinaturas
usuarios (1) -----> (N) empresas
empresas (1) -----> (N) notas_fiscais
planos (1) -----> (N) assinaturas
```

### Diagrama ER Simplificado
```
┌─────────────┐
│  usuarios   │
│  - id       │──┐
│  - email    │  │
│  - nome     │  │
└─────────────┘  │
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
┌──────────────┐   ┌─────────────┐
│ assinaturas  │   │  empresas   │
│  - id        │   │  - id       │──┐
│  - plano_id  │   │  - cnpj     │  │
│  - status    │   │  - razão    │  │
└──────────────┘   └─────────────┘  │
        │                            │
        │                            ▼
        │                   ┌────────────────┐
        │                   │ notas_fiscais  │
        │                   │  - id          │
        │                   │  - chave       │
        │                   │  - valor       │
        ▼                   └────────────────┘
┌─────────────┐
│   planos    │
│  - id       │
│  - nome     │
│  - módulos  │
└─────────────┘
```

## 🔒 Row Level Security (RLS)

Todas as tabelas possuem políticas RLS ativas:

### Usuários
- Podem ver apenas seus próprios dados
- Podem atualizar apenas seus próprios dados

### Empresas
- Usuários veem apenas empresas vinculadas ao seu ID

### Notas Fiscais
- Usuários veem apenas notas das empresas vinculadas

### Exemplo de Política RLS
```sql
CREATE POLICY "Usuários podem ver próprias empresas"
    ON empresas FOR ALL
    USING (usuario_id IN (
        SELECT id FROM usuarios WHERE auth_user_id = auth.uid()
    ));
```

## 📊 Planos Disponíveis

| Plano | Preço Mensal | Preço Anual | Max Empresas | Max Notas/Mês | Módulos |
|-------|--------------|-------------|--------------|---------------|---------|
| **Básico** | R$ 97 | R$ 970 | 3 | 500 | Dashboard, Buscador, Tarefas |
| **Profissional** | R$ 197 | R$ 1.970 | 10 | 2.000 | Todos básicos + Emissor, WhatsApp, Clientes, Estoque, Faturamento |
| **Enterprise** | R$ 497 | R$ 4.970 | 999 | 99.999 | Todos + Serviços, Financeiro, Agenda Médica |

## 🧪 Dados de Teste

O script `schema.sql` cria automaticamente:

### Usuário de Teste
- **Email**: `teste@hicontrol.com.br`
- **Senha**: `HiControl@2024`
- **Plano**: Profissional (ativo por 1 ano)

### Empresa de Teste
- **CNPJ**: `12.345.678/0001-90`
- **Razão Social**: Empresa Teste LTDA

### Notas Fiscais
- 50 notas fiscais aleatórias dos últimos 90 dias
- Tipos variados: NFe, NFSe, NFCe
- Status variados: autorizada, cancelada, denegada

## 🔧 Funções Úteis

### `usuario_tem_acesso_modulo(usuario_id, modulo)`

Verifica se usuário tem acesso a um módulo específico baseado no plano ativo.

```sql
SELECT usuario_tem_acesso_modulo(
    '00000000-0000-0000-0000-000000000001',
    'buscador_notas'
); -- retorna true/false
```

## 📈 Índices para Performance

### Principais Índices Criados

- `idx_usuarios_email` - Busca por email
- `idx_usuarios_ativo` - Filtrar usuários ativos
- `idx_empresas_cnpj` - Busca por CNPJ
- `idx_notas_chave` - Busca por chave de acesso
- `idx_notas_emissao` - Ordenação por data de emissão (DESC)
- `idx_notas_tipo` - Filtro por tipo de nota
- `idx_notas_situacao` - Filtro por situação

## 🔄 Triggers Automáticos

### `update_updated_at_column()`

Atualiza automaticamente o campo `updated_at` em todas as tabelas quando um registro é modificado.

Aplicado em:
- `usuarios`
- `empresas`
- `notas_fiscais`

## 🚀 Migração Futura (PostgreSQL Híbrido)

A estrutura atual está preparada para migração futura:

### Fase Atual (MVP)
- ✅ 100% Supabase
- ✅ RLS ativo
- ✅ Até 100k notas fiscais

### Fase 2 (Planejada)
- 🔄 Supabase: usuários, planos, empresas
- 🔄 PostgreSQL dedicado: notas_fiscais (particionado)
- 🔄 Suporte a 10M+ notas fiscais

### Como Migrar

1. Manter tabela `notas_fiscais` no Supabase como cache/índice
2. Criar banco PostgreSQL dedicado com particionamento
3. Trocar implementação do repositório no código (já abstraído)
4. Zero downtime com dual-write temporário

## 📝 Notas Importantes

### Segurança
- **NUNCA** use `SUPABASE_SERVICE_KEY` em código client-side
- RLS protege dados mesmo com service key vazada
- Certificados A1 devem ser criptografados antes de salvar

### Backup
- Supabase faz backup automático diário
- Backups mantidos por 7 dias (plano Free) ou 30 dias (Pro)

### Limites do Plano Supabase
- **Free**: 500 MB database, 1 GB file storage, 50k monthly active users
- **Pro**: 8 GB database, 100 GB storage, 100k MAU
- Para produção, recomenda-se plano Pro ou superior

## 🔍 Queries Úteis

### Listar usuários com planos ativos
```sql
SELECT
    u.email,
    u.nome_completo,
    p.nome as plano,
    a.data_fim,
    a.status
FROM usuarios u
JOIN assinaturas a ON u.id = a.usuario_id
JOIN planos p ON a.plano_id = p.id
WHERE a.status = 'ativa'
  AND a.data_fim >= CURRENT_DATE
  AND u.deleted_at IS NULL;
```

### Contar notas por empresa
```sql
SELECT
    e.razao_social,
    COUNT(nf.id) as total_notas,
    SUM(nf.valor_total) as valor_total
FROM empresas e
LEFT JOIN notas_fiscais nf ON e.id = nf.empresa_id
WHERE e.ativa = true
  AND e.deleted_at IS NULL
  AND nf.deleted_at IS NULL
GROUP BY e.id, e.razao_social
ORDER BY total_notas DESC;
```

### Verificar assinaturas expirando em 30 dias
```sql
SELECT
    u.email,
    u.nome_completo,
    a.data_fim,
    a.data_fim - CURRENT_DATE as dias_restantes
FROM assinaturas a
JOIN usuarios u ON a.usuario_id = u.id
WHERE a.status = 'ativa'
  AND a.data_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '30 days'
ORDER BY a.data_fim;
```

## 🆘 Troubleshooting

### Erro: "relation does not exist"
- Verifique se executou o `schema.sql` completamente
- Confirme que está conectado ao projeto correto

### Erro: "new row violates row-level security policy"
- Certifique-se de usar a service role key para operações admin
- Verifique se `auth_user_id` está correto

### Performance lenta em queries
- Verifique se índices foram criados corretamente
- Use `EXPLAIN ANALYZE` para entender o plano de execução
- Considere adicionar índices compostos para queries frequentes

## 📚 Referências

- [Supabase Documentation](https://supabase.com/docs)
- [PostgreSQL Row Level Security](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Supabase Python Client](https://supabase.com/docs/reference/python/introduction)
