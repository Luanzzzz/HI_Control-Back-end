-- Usuário Parceiro: luan.valentino78@gmail.com
-- Gerado em: 2026-01-26T14:59:24.057727
-- UUID: 87245dd3-205d-4a7e-81e1-ad7e62056861


-- Inserir usuário parceiro Hi-Control
INSERT INTO usuarios (id, email, nome_completo, hashed_password, ativo, email_verificado, auth_user_id, created_at)
VALUES (
    '87245dd3-205d-4a7e-81e1-ad7e62056861',
    'luan.valentino78@gmail.com',
    'Luan Valentino',
    '$2b$12$ywtvioUX08JIngPXjRmmpeWT7vcNLM.pbC8GPPhYLw8gs7mmwu7kq',
    true,
    true,
    NULL,
    NOW()
) ON CONFLICT (email) DO NOTHING;


-- Criar assinatura enterprise para usuário luan.valentino78@gmail.com
INSERT INTO assinaturas (usuario_id, plano_id, data_inicio, data_fim, status, tipo_cobranca, valor_pago)
SELECT
    '87245dd3-205d-4a7e-81e1-ad7e62056861',
    id,
    CURRENT_DATE,
    '2027-01-26'::DATE,
    'ativa',
    'anual',
    CASE
        WHEN nome = 'basico' THEN 970.00
        WHEN nome = 'profissional' THEN 1970.00
        WHEN nome = 'enterprise' THEN 4970.00
        ELSE 0.00
    END
FROM planos WHERE nome = 'enterprise'
LIMIT 1
ON CONFLICT DO NOTHING;
