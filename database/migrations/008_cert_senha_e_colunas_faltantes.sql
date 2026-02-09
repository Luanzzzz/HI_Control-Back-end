-- ============================================
-- Migration 008: Senha do certificado + colunas faltantes
-- Date: 2026-02-09
-- ============================================

-- 1. Adicionar campo de senha criptografada do certificado nas empresas
-- Permite que o sistema descriptografe o certificado sem solicitar senha ao usuário
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'empresas' AND column_name = 'certificado_senha_encrypted'
    ) THEN
        ALTER TABLE empresas ADD COLUMN certificado_senha_encrypted TEXT;
        COMMENT ON COLUMN empresas.certificado_senha_encrypted IS 'Senha do certificado A1 criptografada com Fernet (para emissão automática)';
    END IF;
END $$;

-- 2. Adicionar campo de senha criptografada do certificado do contador
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'usuarios' AND column_name = 'certificado_contador_senha_encrypted'
    ) THEN
        ALTER TABLE usuarios ADD COLUMN certificado_contador_senha_encrypted TEXT;
        COMMENT ON COLUMN usuarios.certificado_contador_senha_encrypted IS 'Senha do certificado A1 do contador criptografada com Fernet';
    END IF;
END $$;

-- 3. Adicionar aliquota_icms em produtos_cadastrados (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'produtos_cadastrados' AND column_name = 'aliquota_icms'
    ) THEN
        ALTER TABLE produtos_cadastrados ADD COLUMN aliquota_icms NUMERIC(5,2) DEFAULT 0;
    END IF;
END $$;

-- 4. Adicionar campo ean em produtos_cadastrados (se não existir)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'produtos_cadastrados' AND column_name = 'ean'
    ) THEN
        ALTER TABLE produtos_cadastrados ADD COLUMN ean TEXT;
    END IF;
END $$;

-- 5. Garantir que campos NFS-e existam em notas_fiscais
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'xml_resumo'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN xml_resumo TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'xml_completo'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN xml_completo TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'municipio_codigo'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN municipio_codigo TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'municipio_nome'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN municipio_nome TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'codigo_verificacao'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN codigo_verificacao TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'link_visualizacao'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN link_visualizacao TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'descricao_servico'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN descricao_servico TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'codigo_servico'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN codigo_servico TEXT;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'valor_iss'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN valor_iss NUMERIC(15,2);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'notas_fiscais' AND column_name = 'aliquota_iss'
    ) THEN
        ALTER TABLE notas_fiscais ADD COLUMN aliquota_iss NUMERIC(5,4);
    END IF;
END $$;

-- 6. Criar tabela background_jobs (se não existir)
CREATE TABLE IF NOT EXISTS background_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES usuarios(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_background_jobs_user ON background_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_background_jobs_status ON background_jobs(status);

-- Trigger
CREATE OR REPLACE TRIGGER update_background_jobs_updated_at
    BEFORE UPDATE ON background_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- FIM DA MIGRATION
-- ============================================
