-- ============================================
-- Migration 009: Verificação e Correção do Schema Completo
-- Date: 2026-02-10
-- ============================================
-- Esta migration garante que todas as tabelas e colunas
-- necessárias existam no banco de dados.
-- É IDEMPOTENTE - pode ser executada múltiplas vezes sem problema.

-- ============================================
-- 1. VERIFICAR/CRIAR tabela configuracoes_drive
-- ============================================
-- (Caso a migration 005 não tenha sido aplicada)

CREATE TABLE IF NOT EXISTS configuracoes_drive (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    provedor TEXT DEFAULT 'google_drive',
    oauth_access_token_encrypted TEXT,
    oauth_refresh_token_encrypted TEXT,
    oauth_token_expiry TIMESTAMPTZ,
    pasta_id TEXT,
    pasta_nome TEXT,
    ultima_sincronizacao TIMESTAMPTZ,
    total_importadas INTEGER DEFAULT 0,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 2. VERIFICAR/CRIAR tabela configuracoes_email
-- ============================================
CREATE TABLE IF NOT EXISTS configuracoes_email (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    tipo TEXT NOT NULL DEFAULT 'escritorio',
    provedor TEXT NOT NULL DEFAULT 'imap_generico',
    email TEXT NOT NULL,
    imap_host TEXT,
    imap_port INTEGER DEFAULT 993,
    imap_usuario TEXT,
    imap_senha_encrypted TEXT,
    oauth_access_token_encrypted TEXT,
    oauth_refresh_token_encrypted TEXT,
    oauth_token_expiry TIMESTAMPTZ,
    pastas_monitoradas TEXT[] DEFAULT ARRAY['INBOX'],
    ultima_sincronizacao TIMESTAMPTZ,
    total_importadas INTEGER DEFAULT 0,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 3. VERIFICAR/CRIAR tabela log_importacao
-- ============================================
CREATE TABLE IF NOT EXISTS log_importacao (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,
    fonte TEXT NOT NULL DEFAULT 'manual',
    config_id UUID,
    arquivo_nome TEXT,
    tipo_documento TEXT,
    chave_acesso TEXT,
    nota_fiscal_id UUID REFERENCES notas_fiscais(id),
    status TEXT NOT NULL DEFAULT 'sucesso',
    mensagem TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- 4. ADICIONAR COLUNAS FALTANTES em empresas
-- ============================================
DO $$
BEGIN
    -- certificado_senha_encrypted (para emissão automática)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'empresas' AND column_name = 'certificado_senha_encrypted'
    ) THEN
        ALTER TABLE empresas ADD COLUMN certificado_senha_encrypted TEXT;
    END IF;

    -- municipio_codigo (código IBGE)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'empresas' AND column_name = 'municipio_codigo'
    ) THEN
        ALTER TABLE empresas ADD COLUMN municipio_codigo VARCHAR(7);
    END IF;

    -- municipio_nome
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'empresas' AND column_name = 'municipio_nome'
    ) THEN
        ALTER TABLE empresas ADD COLUMN municipio_nome VARCHAR(100);
    END IF;
END $$;

-- ============================================
-- 5. ADICIONAR COLUNAS FALTANTES em notas_fiscais
-- ============================================
DO $$
BEGIN
    -- fonte (manual, email, drive, sefaz)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'fonte'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN fonte TEXT DEFAULT 'manual';
    END IF;

    -- xml_resumo (para resumo da nota)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'xml_resumo'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN xml_resumo TEXT;
    END IF;

    -- xml_completo (para XML completo)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'xml_completo'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN xml_completo TEXT;
    END IF;
END $$;

-- ============================================
-- 6. ÍNDICES DE SEGURANÇA
-- ============================================
CREATE INDEX IF NOT EXISTS idx_config_drive_user ON configuracoes_drive(user_id);
CREATE INDEX IF NOT EXISTS idx_config_drive_empresa ON configuracoes_drive(empresa_id);
CREATE INDEX IF NOT EXISTS idx_config_email_user ON configuracoes_email(user_id);
CREATE INDEX IF NOT EXISTS idx_config_email_empresa ON configuracoes_email(empresa_id);
CREATE INDEX IF NOT EXISTS idx_log_importacao_user ON log_importacao(user_id);
CREATE INDEX IF NOT EXISTS idx_empresas_ativa ON empresas(usuario_id, ativa) WHERE ativa = true;

-- ============================================
-- 7. RLS (se não estiver habilitado)
-- ============================================
ALTER TABLE configuracoes_drive ENABLE ROW LEVEL SECURITY;
ALTER TABLE configuracoes_email ENABLE ROW LEVEL SECURITY;
ALTER TABLE log_importacao ENABLE ROW LEVEL SECURITY;

-- ============================================
-- 8. VERIFICAÇÃO FINAL
-- ============================================
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    -- Verificar coluna ativa em empresas
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'empresas' AND column_name = 'ativa';

    IF col_count = 0 THEN
        RAISE WARNING '⚠️ ATENÇÃO: Coluna empresas.ativa NÃO encontrada! O schema usa "ativa" (feminino).';
    ELSE
        RAISE NOTICE '✅ Coluna empresas.ativa existe';
    END IF;

    -- Verificar tabelas críticas
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'configuracoes_drive') THEN
        RAISE NOTICE '✅ Tabela configuracoes_drive existe';
    ELSE
        RAISE WARNING '❌ Tabela configuracoes_drive NÃO existe';
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'configuracoes_email') THEN
        RAISE NOTICE '✅ Tabela configuracoes_email existe';
    ELSE
        RAISE WARNING '❌ Tabela configuracoes_email NÃO existe';
    END IF;

    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
    RAISE NOTICE '✅ MIGRATION 009 - VERIFICAÇÃO COMPLETA';
    RAISE NOTICE '═══════════════════════════════════════════════════════';
END $$;
