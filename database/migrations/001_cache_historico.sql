-- ============================================
-- MIGRATION: Cache de Notas Fiscais + Histórico de Consultas
-- Hi-Control - Sprint NFe Integration
-- Execute no SQL Editor do Supabase
-- ============================================

-- ============================================
-- 1. TABELA DE CACHE DE NOTAS FISCAIS (TTL 24h)
-- ============================================
CREATE TABLE IF NOT EXISTS cache_notas_fiscais (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identificação
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    chave_busca TEXT NOT NULL, -- hash MD5 dos filtros
    
    -- Dados cacheados
    dados JSONB NOT NULL,
    fonte TEXT CHECK (fonte IN ('sefaz', 'cache')) DEFAULT 'sefaz',
    quantidade_notas INTEGER DEFAULT 0,
    
    -- Controle de expiração
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

-- Índice único para evitar duplicatas por empresa + chave (mais simples, sem data)
CREATE UNIQUE INDEX IF NOT EXISTS idx_cache_unique_empresa_chave 
    ON cache_notas_fiscais(empresa_id, chave_busca);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_cache_notas_expiracao 
    ON cache_notas_fiscais(expires_at);
CREATE INDEX IF NOT EXISTS idx_cache_notas_empresa 
    ON cache_notas_fiscais(empresa_id);

-- Comentários
COMMENT ON TABLE cache_notas_fiscais IS 'Cache de consultas SEFAZ com TTL de 24 horas';
COMMENT ON COLUMN cache_notas_fiscais.chave_busca IS 'Hash MD5: empresa_id:filtros_hash:data';
COMMENT ON COLUMN cache_notas_fiscais.dados IS 'Resultado da consulta SEFAZ em JSON';


-- ============================================
-- 2. TABELA DE HISTÓRICO DE CONSULTAS
-- ============================================
CREATE TABLE IF NOT EXISTS historico_consultas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Identificação
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    contador_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    
    -- Detalhes da consulta
    filtros JSONB NOT NULL,
    quantidade_notas INTEGER,
    fonte TEXT CHECK (fonte IN ('sefaz', 'cache')),
    tempo_resposta_ms INTEGER,
    
    -- Status
    sucesso BOOLEAN DEFAULT TRUE,
    erro_mensagem TEXT,
    
    -- Tipo de certificado usado (para auditoria)
    certificado_tipo TEXT CHECK (certificado_tipo IN ('empresa', 'contador_fallback')),
    
    -- Auditoria
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_historico_empresa 
    ON historico_consultas(empresa_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_historico_contador 
    ON historico_consultas(contador_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_historico_sucesso 
    ON historico_consultas(sucesso, created_at DESC);

-- Comentários
COMMENT ON TABLE historico_consultas IS 'Histórico de consultas SEFAZ para auditoria (retenção 90 dias)';
COMMENT ON COLUMN historico_consultas.certificado_tipo IS 'empresa = certificado do cliente, contador_fallback = usado certificado do contador';


-- ============================================
-- 3. FUNÇÃO DE LIMPEZA DE CACHE EXPIRADO
-- ============================================
CREATE OR REPLACE FUNCTION limpar_cache_expirado()
RETURNS INTEGER AS $$
DECLARE
    registros_deletados INTEGER;
BEGIN
    DELETE FROM cache_notas_fiscais 
    WHERE expires_at < NOW();
    
    GET DIAGNOSTICS registros_deletados = ROW_COUNT;
    
    RAISE NOTICE 'Cache limpo: % registros removidos', registros_deletados;
    RETURN registros_deletados;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION limpar_cache_expirado() IS 'Remove registros de cache expirados. Executar diariamente.';


-- ============================================
-- 4. FUNÇÃO DE LIMPEZA DE HISTÓRICO ANTIGO (90 dias)
-- ============================================
CREATE OR REPLACE FUNCTION limpar_historico_antigo()
RETURNS INTEGER AS $$
DECLARE
    registros_deletados INTEGER;
BEGIN
    DELETE FROM historico_consultas
    WHERE created_at < NOW() - INTERVAL '90 days';
    
    GET DIAGNOSTICS registros_deletados = ROW_COUNT;
    
    RAISE NOTICE 'Histórico limpo: % registros removidos (> 90 dias)', registros_deletados;
    RETURN registros_deletados;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION limpar_historico_antigo() IS 'Remove histórico com mais de 90 dias. Executar diariamente.';


-- ============================================
-- 5. ROW LEVEL SECURITY (RLS)
-- ============================================
ALTER TABLE cache_notas_fiscais ENABLE ROW LEVEL SECURITY;
ALTER TABLE historico_consultas ENABLE ROW LEVEL SECURITY;

-- Política: Contador só acessa cache das suas empresas
CREATE POLICY "Contadores acessam cache das suas empresas"
    ON cache_notas_fiscais FOR ALL
    USING (empresa_id IN (
        SELECT id FROM empresas WHERE usuario_id IN (
            SELECT id FROM usuarios WHERE auth_user_id = auth.uid()
        )
    ));

-- Política: Contador só acessa histórico das suas empresas
CREATE POLICY "Contadores acessam histórico das suas empresas"
    ON historico_consultas FOR ALL
    USING (
        empresa_id IN (
            SELECT id FROM empresas WHERE usuario_id IN (
                SELECT id FROM usuarios WHERE auth_user_id = auth.uid()
            )
        )
        OR contador_id IN (
            SELECT id FROM usuarios WHERE auth_user_id = auth.uid()
        )
    );


-- ============================================
-- 6. TRIGGER PARA ATUALIZAR updated_at (Cache não precisa)
-- ============================================
-- Não aplicável para cache (somente created_at e expires_at)


-- ============================================
-- 7. VERIFICAR/ADICIONAR CAMPOS EM TABELAS EXISTENTES
-- ============================================
-- Campos de certificado na tabela empresas (verificar se existem)
DO $$
BEGIN
    -- Verificar se campo status de certificado existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'empresas' AND column_name = 'certificado_status'
    ) THEN
        ALTER TABLE empresas ADD COLUMN certificado_status TEXT 
            CHECK (certificado_status IN ('ativo', 'vencido', 'ausente', 'expirando'));
        COMMENT ON COLUMN empresas.certificado_status IS 'Status calculado do certificado';
    END IF;
    
    -- Verificar se campo verificado_em existe
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'empresas' AND column_name = 'certificado_verificado_em'
    ) THEN
        ALTER TABLE empresas ADD COLUMN certificado_verificado_em TIMESTAMPTZ;
        COMMENT ON COLUMN empresas.certificado_verificado_em IS 'Última verificação de validade do certificado';
    END IF;
END $$;


-- ============================================
-- FIM DA MIGRATION
-- ============================================
-- NOTA: Para agendar limpeza automática, configurar no Supabase Dashboard:
-- Supabase Dashboard > Database > Extensions > pg_cron
-- Ou usar Supabase Edge Function com cron
--
-- Exemplo pg_cron (se disponível):
-- SELECT cron.schedule('limpar-cache', '0 2 * * *', 'SELECT limpar_cache_expirado()');
-- SELECT cron.schedule('limpar-historico', '0 3 * * *', 'SELECT limpar_historico_antigo()');
