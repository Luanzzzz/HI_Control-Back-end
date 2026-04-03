-- ============================================
-- SCRIPT DE CONFIGURAÇÃO DO USUÁRIO ADMIN ÚNICO
-- ============================================
-- Este script serve como TEMPLATE.
-- Substitua os placeholders antes de executar.
-- Gere o hash bcrypt fora do repositório e nunca registre a senha em texto plano.
-- 
-- IMPORTANTE: Execute este script no SQL Editor do Supabase
-- Dashboard > SQL Editor > New Query > Cole e Execute
-- ============================================

-- Passo 1: Limpar dados de teste e assinaturas existentes
DELETE FROM assinaturas WHERE usuario_id IN (SELECT id FROM usuarios);
DELETE FROM empresas WHERE usuario_id IN (SELECT id FROM usuarios);
DELETE FROM notas_fiscais;

-- Passo 2: Limpar todos os usuários
DELETE FROM usuarios;

-- Passo 3: Criar o usuário administrador único
-- Substitua:
--   <ADMIN_EMAIL>
--   <ADMIN_NAME>
--   <BCRYPT_HASH>
INSERT INTO usuarios (
    id,
    email,
    nome_completo,
    hashed_password,
    ativo,
    email_verificado,
    created_at,
    updated_at
)
VALUES (
    gen_random_uuid(),
    '<ADMIN_EMAIL>',
    '<ADMIN_NAME>',
    '<BCRYPT_HASH>',
    true,
    true,
    NOW(),
    NOW()
);

-- Passo 4: Criar assinatura Premium (Profissional) para o administrador
-- A assinatura será válida por 1 ano
INSERT INTO assinaturas (
    id,
    usuario_id,
    plano_id,
    data_inicio,
    data_fim,
    tipo_cobranca,
    status,
    valor_pago,
    em_trial,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    u.id,
    p.id,
    CURRENT_DATE,
    CURRENT_DATE + INTERVAL '1 year',
    'anual',
    'ativa',
    1970.00,
    false,
    NOW(),
    NOW()
FROM usuarios u
CROSS JOIN planos p
WHERE u.email = '<ADMIN_EMAIL>'
  AND p.nome = 'profissional'
LIMIT 1;

-- Passo 5: Verificar se tudo foi criado corretamente
SELECT
    u.id,
    u.email,
    u.nome_completo,
    u.ativo,
    u.email_verificado,
    p.nome AS plano,
    a.status AS status_assinatura,
    a.data_inicio,
    a.data_fim,
    p.modulos_disponiveis
FROM usuarios u
LEFT JOIN assinaturas a ON u.id = a.usuario_id AND a.status = 'ativa'
LEFT JOIN planos p ON a.plano_id = p.id
WHERE u.email = '<ADMIN_EMAIL>';

-- ============================================
-- FIM DO SCRIPT
-- ============================================
-- Resultado esperado:
-- - 1 usuário criado: <ADMIN_EMAIL>
-- - Plano: profissional (premium)
-- - Status: ativa
-- - Módulos: ["dashboard", "buscador_notas", "emissor_notas", "tarefas", "whatsapp", "clientes", "estoque", "faturamento"]
-- ============================================
