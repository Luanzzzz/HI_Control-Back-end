-- ============================================
-- Migration 005: Configurações Email IMAP e Google Drive
-- Para importação automática de XMLs fiscais
-- ============================================

-- Tabela de configurações de email
CREATE TABLE IF NOT EXISTS configuracoes_email (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL CHECK (tipo IN ('escritorio', 'empresa')),
    provedor TEXT NOT NULL CHECK (provedor IN ('gmail', 'outlook', 'imap_generico')),
    email TEXT NOT NULL,

    -- IMAP genérico
    imap_host TEXT,
    imap_port INTEGER DEFAULT 993,
    imap_usuario TEXT,
    imap_senha_encrypted TEXT,

    -- OAuth (Gmail/Outlook)
    oauth_access_token_encrypted TEXT,
    oauth_refresh_token_encrypted TEXT,
    oauth_token_expiry TIMESTAMPTZ,

    -- Configuração
    pastas_monitoradas TEXT[] DEFAULT ARRAY['INBOX'],
    ultima_sincronizacao TIMESTAMPTZ,
    total_importadas INTEGER DEFAULT 0,
    ativo BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de configurações Google Drive
CREATE TABLE IF NOT EXISTS configuracoes_drive (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    provedor TEXT DEFAULT 'google_drive',

    -- OAuth
    oauth_access_token_encrypted TEXT,
    oauth_refresh_token_encrypted TEXT,
    oauth_token_expiry TIMESTAMPTZ,

    -- Pasta monitorada
    pasta_id TEXT,
    pasta_nome TEXT,

    ultima_sincronizacao TIMESTAMPTZ,
    total_importadas INTEGER DEFAULT 0,
    ativo BOOLEAN DEFAULT true,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de log de importação (email e drive)
CREATE TABLE IF NOT EXISTS log_importacao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    fonte TEXT NOT NULL CHECK (fonte IN ('email', 'drive', 'xml_manual')),
    config_id UUID,
    arquivo_nome TEXT,
    tipo_documento TEXT,
    chave_acesso TEXT,
    nota_fiscal_id UUID REFERENCES notas_fiscais(id),
    status TEXT NOT NULL CHECK (status IN ('sucesso', 'erro', 'duplicada', 'ignorada')),
    mensagem TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_config_email_user ON configuracoes_email(user_id);
CREATE INDEX IF NOT EXISTS idx_config_email_empresa ON configuracoes_email(empresa_id);
CREATE INDEX IF NOT EXISTS idx_config_email_ativo ON configuracoes_email(ativo) WHERE ativo = true;

CREATE INDEX IF NOT EXISTS idx_config_drive_user ON configuracoes_drive(user_id);
CREATE INDEX IF NOT EXISTS idx_config_drive_empresa ON configuracoes_drive(empresa_id);
CREATE INDEX IF NOT EXISTS idx_config_drive_ativo ON configuracoes_drive(ativo) WHERE ativo = true;

CREATE INDEX IF NOT EXISTS idx_log_importacao_user ON log_importacao(user_id);
CREATE INDEX IF NOT EXISTS idx_log_importacao_empresa ON log_importacao(empresa_id);
CREATE INDEX IF NOT EXISTS idx_log_importacao_fonte ON log_importacao(fonte);
CREATE INDEX IF NOT EXISTS idx_log_importacao_created ON log_importacao(created_at DESC);

-- Triggers de updated_at
CREATE OR REPLACE TRIGGER update_config_email_updated_at
    BEFORE UPDATE ON configuracoes_email
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_config_drive_updated_at
    BEFORE UPDATE ON configuracoes_drive
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- RLS
ALTER TABLE configuracoes_email ENABLE ROW LEVEL SECURITY;
ALTER TABLE configuracoes_drive ENABLE ROW LEVEL SECURITY;
ALTER TABLE log_importacao ENABLE ROW LEVEL SECURITY;

-- Policies: usuário só vê suas próprias configurações
CREATE POLICY "config_email_user_select" ON configuracoes_email
    FOR SELECT USING (auth.uid()::text = user_id::text);

CREATE POLICY "config_email_user_insert" ON configuracoes_email
    FOR INSERT WITH CHECK (auth.uid()::text = user_id::text);

CREATE POLICY "config_email_user_update" ON configuracoes_email
    FOR UPDATE USING (auth.uid()::text = user_id::text);

CREATE POLICY "config_email_user_delete" ON configuracoes_email
    FOR DELETE USING (auth.uid()::text = user_id::text);

CREATE POLICY "config_drive_user_select" ON configuracoes_drive
    FOR SELECT USING (auth.uid()::text = user_id::text);

CREATE POLICY "config_drive_user_insert" ON configuracoes_drive
    FOR INSERT WITH CHECK (auth.uid()::text = user_id::text);

CREATE POLICY "config_drive_user_update" ON configuracoes_drive
    FOR UPDATE USING (auth.uid()::text = user_id::text);

CREATE POLICY "config_drive_user_delete" ON configuracoes_drive
    FOR DELETE USING (auth.uid()::text = user_id::text);

CREATE POLICY "log_importacao_user_select" ON log_importacao
    FOR SELECT USING (auth.uid()::text = user_id::text);

CREATE POLICY "log_importacao_user_insert" ON log_importacao
    FOR INSERT WITH CHECK (auth.uid()::text = user_id::text);

-- Adicionar campo 'fonte' na notas_fiscais se não existir
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'fonte'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN fonte TEXT DEFAULT 'manual';
    END IF;
END $$;
