-- ============================================
-- SCRIPT DEFINITIVO - CRIAR USUÁRIO ADMIN
-- ============================================
-- Execute este script no SQL Editor do Supabase
-- ============================================

-- Passo 1: Limpar dados existentes
DELETE FROM assinaturas;
DELETE FROM empresas;
DELETE FROM notas_fiscais;
DELETE FROM usuarios;

-- Passo 2: Criar usuário admin
-- IMPORTANTE: Este INSERT não usa ON CONFLICT
INSERT INTO usuarios (
    email,
    nome_completo,
    hashed_password,
    ativo,
    email_verificado,
    created_at,
    updated_at
)
VALUES (
    'luan.valentino78@gmail.com',
    'Luan Valentino',
    '$2b$12$l5XuXtzigdE/jstnqmsChuapednBbnDd1MwHuMXqEH9f2ivWinSea',
    true,
    true,
    NOW(),
    NOW()
);

-- Passo 3: Criar assinatura premium
INSERT INTO assinaturas (
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
WHERE u.email = 'luan.valentino78@gmail.com'
  AND p.nome = 'profissional';

-- Passo 4: Verificar criação
SELECT
    u.id,
    u.email,
    u.nome_completo,
    u.ativo,
    p.nome AS plano,
    a.status AS status_assinatura,
    a.data_fim,
    p.modulos_disponiveis
FROM usuarios u
LEFT JOIN assinaturas a ON u.id = a.usuario_id
LEFT JOIN planos p ON a.plano_id = p.id
WHERE u.email = 'luan.valentino78@gmail.com';

-- ============================================
-- FIM - Deve retornar 1 linha com os dados do usuário
-- ============================================
