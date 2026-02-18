-- ============================================================
-- HI-CONTROL - Migration 011: Bot de Captura SEFAZ Nacional
-- ============================================================

-- 1. Controle de sincronizacao por empresa
CREATE TABLE IF NOT EXISTS sync_empresas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE UNIQUE,

    -- NSU e o cursor de paginacao do DistribuicaoDFe
    ultimo_nsu BIGINT DEFAULT 0,
    max_nsu BIGINT DEFAULT 0,

    -- Status da ultima sincronizacao
    ultima_sync TIMESTAMP WITH TIME ZONE,
    proximo_sync TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'pendente',
    -- pendente | sincronizando | ok | erro | sem_certificado

    -- Metricas
    total_notas_capturadas INTEGER DEFAULT 0,
    notas_capturadas_ultima_sync INTEGER DEFAULT 0,
    erro_mensagem TEXT,
    tentativas_consecutivas_erro INTEGER DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Log de sincronizacoes (historico para auditoria)
CREATE TABLE IF NOT EXISTS sync_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    iniciado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finalizado_em TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20), -- ok | erro | parcial
    notas_novas INTEGER DEFAULT 0,
    notas_atualizadas INTEGER DEFAULT 0,
    nsu_inicio BIGINT,
    nsu_fim BIGINT,
    erro_detalhes TEXT,
    duracao_ms INTEGER
);

-- 3. Adicionar apenas colunas novas em notas_fiscais
ALTER TABLE notas_fiscais
    ADD COLUMN IF NOT EXISTS nsu BIGINT,
    ADD COLUMN IF NOT EXISTS tipo_operacao VARCHAR(10) DEFAULT 'entrada';
    -- entrada (tomada) | saida (prestada)

-- 4. Indices
CREATE INDEX IF NOT EXISTS idx_sync_empresas_proximo_sync
    ON sync_empresas(proximo_sync) WHERE status != 'sincronizando';
CREATE INDEX IF NOT EXISTS idx_notas_nsu ON notas_fiscais(nsu);
CREATE INDEX IF NOT EXISTS idx_sync_log_empresa ON sync_log(empresa_id, iniciado_em DESC);

-- 5. Trigger de updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_sync_empresas_updated_at ON sync_empresas;
CREATE TRIGGER update_sync_empresas_updated_at
    BEFORE UPDATE ON sync_empresas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 6. Inicializar sync_empresas para empresas ativas existentes
INSERT INTO sync_empresas (empresa_id)
SELECT id
FROM empresas
WHERE ativa = true AND deleted_at IS NULL
ON CONFLICT (empresa_id) DO NOTHING;
