-- ============================================
-- DIAGNÓSTICO: Verificar se usuário parceiro existe
-- ============================================

-- 1. Verificar se o usuário socio.teste@hicontrol.com.br existe
SELECT 
    id,
    email,
    nome_completo,
    ativo,
    email_verificado,
    created_at,
    hashed_password IS NOT NULL as has_password
FROM usuarios
WHERE email = 'socio.teste@hicontrol.com.br';

-- 2. Se usuário existe, verificar assinatura
SELECT 
    a.id,
    a.usuario_id,
    a.status,
    a.data_inicio,
    a.data_fim,
    p.nome as plano_nome
FROM assinaturas a
JOIN planos p ON a.plano_id = p.id
WHERE a.usuario_id IN (
    SELECT id FROM usuarios WHERE email = 'socio.teste@hicontrol.com.br'
);

-- 3. Verificar todos os usuários (para debug)
SELECT 
    email,
    nome_completo,
    ativo,
    email_verificado
FROM usuarios
ORDER BY created_at DESC
LIMIT 5;
