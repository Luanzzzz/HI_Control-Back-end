-- ============================================
-- CORREÇÃO: Atualizar Senha do Usuário Admin
-- ============================================
-- Gerado em: 2026-01-26
-- Senha: 2520@Selu
-- Hash Bcrypt: $2b$12$ywtvioUX08JIngPXjRmmpeWT7vcNLM.pbC8GPPhYLw8gs7mmwu7kq

-- OPÇÃO 1: Apenas Atualizar Hash (Recomendado - Preserva ID e histórico)
UPDATE usuarios
SET hashed_password = '$2b$12$ywtvioUX08JIngPXjRmmpeWT7vcNLM.pbC8GPPhYLw8gs7mmwu7kq',
    updated_at = NOW()
WHERE email = 'luan.valentino78@gmail.com';

-- Verificar atualização
SELECT email, nome_completo, ativo, email_verificado, 
       substring(hashed_password, 1, 30) as hash_preview,
       updated_at
FROM usuarios
WHERE email = 'luan.valentino78@gmail.com';

-- ============================================
-- OPÇÃO 2: Deletar e Recriar (Se Opção 1 falhar)
-- ============================================
/*
-- Deletar usuário anterior (CASCADE deleta assinaturas)
DELETE FROM usuarios WHERE email = 'luan.valentino78@gmail.com';

-- Inserir novo usuário
INSERT INTO usuarios (id, email, nome_completo, hashed_password, ativo, email_verificado, auth_user_id, created_at)
VALUES (
    gen_random_uuid(),
    'luan.valentino78@gmail.com',
    'Luan Valentino',
    '$2b$12$ywtvioUX08JIngPXjRmmpeWT7vcNLM.pbC8GPPhYLw8gs7mmwu7kq',
    true,
    true,
    NULL,
    NOW()
);

-- Criar assinatura enterprise
INSERT INTO assinaturas (usuario_id, plano_id, data_inicio, data_fim, status, tipo_cobranca, valor_pago)
SELECT
    id AS usuario_id,
    (SELECT id FROM planos WHERE nome = 'enterprise'),
    CURRENT_DATE,
    '2027-01-26'::DATE,
    'ativa',
    'anual',
    4970.00
FROM usuarios
WHERE email = 'luan.valentino78@gmail.com'
LIMIT 1;
*/

-- ============================================
-- CREDENCIAIS PARA TESTE
-- ============================================
-- Email: luan.valentino78@gmail.com
-- Senha: 2520@Selu
