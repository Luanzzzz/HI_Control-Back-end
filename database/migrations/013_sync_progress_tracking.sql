-- ============================================================
-- HI-CONTROL - Migration 013: Progresso em tempo real da captura
-- ============================================================

ALTER TABLE sync_empresas
    ADD COLUMN IF NOT EXISTS inicio_sync_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS etapa_atual VARCHAR(120),
    ADD COLUMN IF NOT EXISTS mensagem_progresso TEXT,
    ADD COLUMN IF NOT EXISTS progresso_percentual NUMERIC(5,2) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS notas_processadas_parcial INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS notas_estimadas_total INTEGER,
    ADD COLUMN IF NOT EXISTS tempo_restante_estimado_segundos INTEGER;

CREATE INDEX IF NOT EXISTS idx_sync_empresas_status_progresso
    ON sync_empresas(status, updated_at DESC);
