-- ============================================
-- MIGRATION: Add Accounting Certificate Fields
-- Date: 2026-01-27
-- Description: Add certificate and accounting firm data fields to usuarios and empresas tables
-- ============================================

-- ============================================
-- 1. ADD ACCOUNTING FIRM DATA TO USUARIOS TABLE
-- ============================================

-- Dados da Firma de Contabilidade
ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS razao_social_contador VARCHAR(255),
ADD COLUMN IF NOT EXISTS cnpj_contador VARCHAR(18),
ADD COLUMN IF NOT EXISTS inscricao_estadual_contador VARCHAR(50),
ADD COLUMN IF NOT EXISTS logo_url_contador TEXT;

-- Certificado Digital do Contador (A1)
ALTER TABLE usuarios
ADD COLUMN IF NOT EXISTS certificado_contador_a1 TEXT,
ADD COLUMN IF NOT EXISTS certificado_contador_validade DATE,
ADD COLUMN IF NOT EXISTS certificado_contador_titular TEXT,
ADD COLUMN IF NOT EXISTS certificado_contador_emissor TEXT;

-- ============================================
-- 2. ADD CERTIFICATE INFO FIELDS TO EMPRESAS TABLE
-- ============================================

-- Adicionar campos de informação do certificado (evita descriptografia para exibição)
ALTER TABLE empresas
ADD COLUMN IF NOT EXISTS certificado_titular TEXT,
ADD COLUMN IF NOT EXISTS certificado_emissor TEXT;

-- ============================================
-- 3. CREATE INDEXES FOR PERFORMANCE
-- ============================================

-- Índice para CNPJ do contador (busca rápida)
CREATE INDEX IF NOT EXISTS idx_usuarios_cnpj_contador
ON usuarios(cnpj_contador)
WHERE cnpj_contador IS NOT NULL;

-- Índice para validade do certificado do contador (alertas de expiração)
CREATE INDEX IF NOT EXISTS idx_usuarios_cert_validade
ON usuarios(certificado_contador_validade)
WHERE certificado_contador_validade IS NOT NULL;

-- Índice para titular do certificado da empresa (busca por titular)
CREATE INDEX IF NOT EXISTS idx_empresas_cert_titular
ON empresas(certificado_titular)
WHERE certificado_titular IS NOT NULL;

-- ============================================
-- 4. ADD COMMENTS FOR DOCUMENTATION
-- ============================================

COMMENT ON COLUMN usuarios.razao_social_contador IS 'Razão Social da firma de contabilidade do contador';
COMMENT ON COLUMN usuarios.cnpj_contador IS 'CNPJ da firma de contabilidade (formato: 99.999.999/9999-99)';
COMMENT ON COLUMN usuarios.inscricao_estadual_contador IS 'Inscrição Estadual da firma de contabilidade';
COMMENT ON COLUMN usuarios.logo_url_contador IS 'URL ou base64 da logo da firma de contabilidade';
COMMENT ON COLUMN usuarios.certificado_contador_a1 IS 'Certificado Digital A1 do contador (criptografado com Fernet)';
COMMENT ON COLUMN usuarios.certificado_contador_validade IS 'Data de validade do certificado digital do contador';
COMMENT ON COLUMN usuarios.certificado_contador_titular IS 'Titular do certificado (CN do Subject) - para exibição sem descriptografia';
COMMENT ON COLUMN usuarios.certificado_contador_emissor IS 'Emissor do certificado (CN do Issuer) - para exibição sem descriptografia';

COMMENT ON COLUMN empresas.certificado_titular IS 'Titular do certificado da empresa (CN do Subject)';
COMMENT ON COLUMN empresas.certificado_emissor IS 'Emissor do certificado da empresa (CN do Issuer)';

-- ============================================
-- 5. VERIFICATION QUERIES
-- ============================================

-- Verificar se as colunas foram criadas corretamente
-- Execute após a migração para validar:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'usuarios'
-- AND column_name LIKE '%contador%';

-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'empresas'
-- AND column_name LIKE 'certificado_%';

-- ============================================
-- FIM DA MIGRATION
-- ============================================
