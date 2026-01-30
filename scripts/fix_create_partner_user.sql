-- ============================================
-- SOLUÇÃO: Deletar e Recriar Usuário Parceiro
-- ============================================
-- Este script garante a criação do usuário removendo qualquer conflito anterior

-- PASSO 1: Deletar usuário anterior se existir (CASCADE deleta assinaturas também)
DELETE FROM usuarios WHERE email = 'socio.teste@hicontrol.com.br';

-- PASSO 2: Inserir novo usuário parceiro Hi-Control
INSERT INTO usuarios (id, email, nome_completo, hashed_password, ativo, email_verificado, auth_user_id, created_at)
VALUES (
    '8fb27d28-68d7-4483-95ef-b14c7d4b45da',
    'socio.teste@hicontrol.com.br',
    'Sócio Hi-Control (Teste)',
    '$2b$12$kicjDDmKe2h.sHuFGuJus.MjjFzb7ZUS9gkTN1REPgB1CByOx7FYq',
    true,
    true,
    NULL,
    NOW()
);

-- PASSO 3: Criar assinatura enterprise
INSERT INTO assinaturas (usuario_id, plano_id, data_inicio, data_fim, status, tipo_cobranca, valor_pago)
SELECT
    '8fb27d28-68d7-4483-95ef-b14c7d4b45da',
    id,
    CURRENT_DATE,
    '2027-01-26'::DATE,
    'ativa',
    'anual',
    4970.00
FROM planos WHERE nome = 'enterprise'
LIMIT 1;

-- PASSO 4: Verificar criação (DEVE RETORNAR 1 LINHA)
SELECT 
    u.email,
    u.nome_completo,
    u.ativo,
    u.email_verificado,
    a.status as assinatura_status,
    p.nome as plano
FROM usuarios u
LEFT JOIN assinaturas a ON u.id = a.usuario_id
LEFT JOIN planos p ON a.plano_id = p.id
WHERE u.email = 'socio.teste@hicontrol.com.br';
