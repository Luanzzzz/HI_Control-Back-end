-- ============================================================
-- HI-CONTROL - Migration 014: Plano Admin + Configuracao de Sync
-- ============================================================

-- 1) Garantir plano admin
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM planos WHERE LOWER(nome) = 'admin') THEN
        INSERT INTO planos (
            nome,
            descricao,
            preco_mensal,
            preco_anual,
            max_usuarios,
            max_empresas,
            max_notas_mes,
            modulos_disponiveis,
            possui_api,
            possui_whatsapp,
            possui_relatorios_avancados,
            ativo
        ) VALUES (
            'admin',
            'Plano administrativo com controle manual de sincronizacao e acesso total.',
            0,
            0,
            999,
            9999,
            999999,
            '["dashboard","buscador_notas","emissor_notas","tarefas","whatsapp","clientes","estoque","faturamento","servicos","financeiro","agenda_medica","certificados","sync_manual"]'::jsonb,
            TRUE,
            TRUE,
            TRUE,
            TRUE
        );
    ELSE
        UPDATE planos
        SET
            descricao = 'Plano administrativo com controle manual de sincronizacao e acesso total.',
            modulos_disponiveis = '["dashboard","buscador_notas","emissor_notas","tarefas","whatsapp","clientes","estoque","faturamento","servicos","financeiro","agenda_medica","certificados","sync_manual"]'::jsonb,
            max_usuarios = 999,
            max_empresas = 9999,
            max_notas_mes = 999999,
            possui_api = TRUE,
            possui_whatsapp = TRUE,
            possui_relatorios_avancados = TRUE,
            ativo = TRUE,
            updated_at = NOW()
        WHERE LOWER(nome) = 'admin';
    END IF;
END $$;

-- 2) Configuracao global de sincronizacao por contador
CREATE TABLE IF NOT EXISTS sync_configuracoes_contador (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE UNIQUE,
    auto_sync_ativo BOOLEAN NOT NULL DEFAULT TRUE,
    intervalo_horas INTEGER NOT NULL DEFAULT 4 CHECK (intervalo_horas BETWEEN 1 AND 24),
    prioridade_recente BOOLEAN NOT NULL DEFAULT TRUE,
    reparar_incompletas BOOLEAN NOT NULL DEFAULT TRUE,
    tipos_notas TEXT[] NOT NULL DEFAULT ARRAY['NFSE', 'NFE', 'NFCE', 'CTE'],
    horario_inicio TIME NOT NULL DEFAULT '00:00:00',
    horario_fim TIME NOT NULL DEFAULT '23:59:59',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3) Configuracao de sincronizacao por empresa (override)
CREATE TABLE IF NOT EXISTS sync_configuracoes_empresa (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE UNIQUE,
    usuario_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    usar_configuracao_contador BOOLEAN NOT NULL DEFAULT TRUE,
    auto_sync_ativo BOOLEAN NOT NULL DEFAULT TRUE,
    intervalo_horas INTEGER NOT NULL DEFAULT 4 CHECK (intervalo_horas BETWEEN 1 AND 24),
    prioridade_recente BOOLEAN NOT NULL DEFAULT TRUE,
    reparar_incompletas BOOLEAN NOT NULL DEFAULT TRUE,
    tipos_notas TEXT[] NOT NULL DEFAULT ARRAY['NFSE', 'NFE', 'NFCE', 'CTE'],
    horario_inicio TIME NOT NULL DEFAULT '00:00:00',
    horario_fim TIME NOT NULL DEFAULT '23:59:59',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sync_cfg_contador_usuario
    ON sync_configuracoes_contador(usuario_id);
CREATE INDEX IF NOT EXISTS idx_sync_cfg_empresa_usuario
    ON sync_configuracoes_empresa(usuario_id);
CREATE INDEX IF NOT EXISTS idx_sync_cfg_empresa_uso_geral
    ON sync_configuracoes_empresa(usar_configuracao_contador);

-- 4) Trigger updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_sync_configuracoes_contador_updated_at ON sync_configuracoes_contador;
CREATE TRIGGER update_sync_configuracoes_contador_updated_at
    BEFORE UPDATE ON sync_configuracoes_contador
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_sync_configuracoes_empresa_updated_at ON sync_configuracoes_empresa;
CREATE TRIGGER update_sync_configuracoes_empresa_updated_at
    BEFORE UPDATE ON sync_configuracoes_empresa
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 5) Inicializar configuracoes para usuarios/empresas existentes
INSERT INTO sync_configuracoes_contador (usuario_id)
SELECT id
FROM usuarios
WHERE deleted_at IS NULL
ON CONFLICT (usuario_id) DO NOTHING;

INSERT INTO sync_configuracoes_empresa (empresa_id, usuario_id)
SELECT e.id, e.usuario_id
FROM empresas e
WHERE e.deleted_at IS NULL
ON CONFLICT (empresa_id) DO NOTHING;

-- 6) Promover usuarios especificos para plano admin
WITH admin_plan AS (
    SELECT id
    FROM planos
    WHERE LOWER(nome) = 'admin'
    ORDER BY created_at ASC
    LIMIT 1
),
usuarios_alvo AS (
    SELECT id
    FROM usuarios
    WHERE LOWER(email) IN (
        'luan.valentino78@gmail.com',
        'pauloadmin@hicontrol.com',
        'marceloadmin@hicontrol.com'
    )
)
UPDATE assinaturas a
SET
    status = 'cancelada',
    cancelada_em = NOW(),
    updated_at = NOW()
FROM usuarios_alvo u, admin_plan p
WHERE a.usuario_id = u.id
  AND a.status = 'ativa'
  AND a.plano_id <> p.id;

WITH admin_plan AS (
    SELECT id
    FROM planos
    WHERE LOWER(nome) = 'admin'
    ORDER BY created_at ASC
    LIMIT 1
),
usuarios_alvo AS (
    SELECT id
    FROM usuarios
    WHERE LOWER(email) IN (
        'luan.valentino78@gmail.com',
        'pauloadmin@hicontrol.com',
        'marceloadmin@hicontrol.com'
    )
)
UPDATE assinaturas a
SET
    status = 'ativa',
    data_fim = GREATEST(a.data_fim, (CURRENT_DATE + INTERVAL '5 years')::date),
    updated_at = NOW()
FROM usuarios_alvo u, admin_plan p
WHERE a.usuario_id = u.id
  AND a.plano_id = p.id;

WITH admin_plan AS (
    SELECT id
    FROM planos
    WHERE LOWER(nome) = 'admin'
    ORDER BY created_at ASC
    LIMIT 1
),
usuarios_alvo AS (
    SELECT id
    FROM usuarios
    WHERE LOWER(email) IN (
        'luan.valentino78@gmail.com',
        'pauloadmin@hicontrol.com',
        'marceloadmin@hicontrol.com'
    )
)
INSERT INTO assinaturas (
    usuario_id,
    plano_id,
    data_inicio,
    data_fim,
    tipo_cobranca,
    status,
    valor_pago,
    created_at,
    updated_at
)
SELECT
    u.id,
    p.id,
    CURRENT_DATE,
    (CURRENT_DATE + INTERVAL '5 years')::date,
    'anual',
    'ativa',
    0,
    NOW(),
    NOW()
FROM usuarios_alvo u
CROSS JOIN admin_plan p
WHERE NOT EXISTS (
    SELECT 1
    FROM assinaturas a
    WHERE a.usuario_id = u.id
      AND a.plano_id = p.id
      AND a.status = 'ativa'
      AND a.data_fim >= CURRENT_DATE
);
