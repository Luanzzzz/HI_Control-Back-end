-- Usuário Parceiro: socio.teste@hicontrol.com.br
-- Gerado em: 2026-01-26T12:50:30.007070
-- UUID: 8fb27d28-68d7-4483-95ef-b14c7d4b45da


-- Inserir usuário parceiro Hi-Control
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
) ON CONFLICT (email) DO NOTHING;


-- Criar assinatura enterprise para usuário socio.teste@hicontrol.com.br
INSERT INTO assinaturas (usuario_id, plano_id, data_inicio, data_fim, status, tipo_cobranca, valor_pago)
SELECT
    '8fb27d28-68d7-4483-95ef-b14c7d4b45da',
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
