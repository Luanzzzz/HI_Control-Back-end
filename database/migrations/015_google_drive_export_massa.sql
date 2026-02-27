-- ============================================================
-- HI-CONTROL - Migration 015: Exportacao em Massa XML -> Google Drive
-- ============================================================

-- 1) Expandir configuracoes de Drive para exportacao em massa
ALTER TABLE configuracoes_drive
    ADD COLUMN IF NOT EXISTS pasta_raiz_export_id TEXT,
    ADD COLUMN IF NOT EXISTS pasta_raiz_export_nome TEXT DEFAULT 'Hi-Control Exportacoes';

UPDATE configuracoes_drive
SET pasta_raiz_export_nome = COALESCE(NULLIF(pasta_raiz_export_nome, ''), 'Hi-Control Exportacoes')
WHERE pasta_raiz_export_nome IS NULL OR pasta_raiz_export_nome = '';

-- 2) Mapeamento de pastas por empresa (1 pasta por cliente no Drive)
CREATE TABLE IF NOT EXISTS drive_pastas_empresas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    pasta_raiz_id TEXT,
    pasta_empresa_id TEXT NOT NULL,
    pasta_empresa_nome TEXT NOT NULL,
    criado_automaticamente BOOLEAN NOT NULL DEFAULT TRUE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_drive_pasta_empresa UNIQUE (user_id, empresa_id)
);

-- 3) Jobs de exportacao em massa
CREATE TABLE IF NOT EXISTS drive_export_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    config_drive_id UUID REFERENCES configuracoes_drive(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pendente',
    -- pendente | processando | concluido | concluido_com_erros | erro | cancelado
    destino VARCHAR(30) NOT NULL DEFAULT 'google_drive',
    empresa_ids UUID[] DEFAULT ARRAY[]::UUID[],
    filtros JSONB DEFAULT '{}'::JSONB,
    total_notas INTEGER NOT NULL DEFAULT 0,
    notas_processadas INTEGER NOT NULL DEFAULT 0,
    notas_exportadas INTEGER NOT NULL DEFAULT 0,
    notas_duplicadas INTEGER NOT NULL DEFAULT 0,
    notas_erro INTEGER NOT NULL DEFAULT 0,
    progresso_percentual NUMERIC(5,2) NOT NULL DEFAULT 0,
    mensagem TEXT,
    pasta_raiz_id TEXT,
    iniciado_em TIMESTAMPTZ,
    finalizado_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4) Itens processados do job
CREATE TABLE IF NOT EXISTS drive_export_job_itens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES drive_export_jobs(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    nota_id UUID REFERENCES notas_fiscais(id) ON DELETE SET NULL,
    chave_acesso TEXT,
    numero_nf TEXT,
    mes_referencia VARCHAR(7),
    tipo_operacao VARCHAR(10),
    arquivo_nome TEXT,
    pasta_destino_id TEXT,
    drive_file_id TEXT,
    status VARCHAR(20) NOT NULL,
    -- exportada | duplicada | erro
    mensagem TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_drive_export_item_job_nota UNIQUE (job_id, nota_id)
);

-- 5) Indices
CREATE INDEX IF NOT EXISTS idx_drive_pastas_empresas_user
    ON drive_pastas_empresas(user_id);
CREATE INDEX IF NOT EXISTS idx_drive_pastas_empresas_empresa
    ON drive_pastas_empresas(empresa_id);

CREATE INDEX IF NOT EXISTS idx_drive_export_jobs_user_status
    ON drive_export_jobs(user_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_drive_export_jobs_created
    ON drive_export_jobs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_drive_export_itens_job
    ON drive_export_job_itens(job_id, status);
CREATE INDEX IF NOT EXISTS idx_drive_export_itens_empresa
    ON drive_export_job_itens(empresa_id, created_at DESC);

-- 6) Trigger updated_at
DROP TRIGGER IF EXISTS update_drive_pastas_empresas_updated_at ON drive_pastas_empresas;
CREATE TRIGGER update_drive_pastas_empresas_updated_at
    BEFORE UPDATE ON drive_pastas_empresas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_drive_export_jobs_updated_at ON drive_export_jobs;
CREATE TRIGGER update_drive_export_jobs_updated_at
    BEFORE UPDATE ON drive_export_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_drive_export_job_itens_updated_at ON drive_export_job_itens;
CREATE TRIGGER update_drive_export_job_itens_updated_at
    BEFORE UPDATE ON drive_export_job_itens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

