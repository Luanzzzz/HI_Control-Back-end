-- ============================================
-- HI-CONTROL - NFS-e: CREDENCIAIS E CAMPOS
-- ============================================
-- Data: 2026-02-09
-- Versão: 003
-- Descrição: Criação da tabela de credenciais NFS-e
--            e expansão da tabela notas_fiscais para
--            suportar Notas Fiscais de Serviço.

-- ============================================
-- IMPORTANTE: Execute no SQL Editor do Supabase
-- Dashboard > SQL Editor > New Query
-- ============================================


-- ============================================
-- 1. TABELA DE CREDENCIAIS NFS-e
-- ============================================
-- Armazena credenciais de acesso às APIs municipais
-- de NFS-e por empresa + município

CREATE TABLE IF NOT EXISTS credenciais_nfse (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    
    -- Relacionamento com empresa
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    
    -- Município da credencial
    municipio_codigo VARCHAR(7) NOT NULL,  -- Código IBGE (7 dígitos)
    
    -- Credenciais de acesso
    usuario VARCHAR(255),                  -- Login da API municipal
    senha VARCHAR(255),                    -- Senha da API municipal
    token TEXT,                            -- Token de acesso (se aplicável)
    cnpj VARCHAR(14),                      -- CNPJ para contexto de autenticação
    
    -- Status
    ativo BOOLEAN DEFAULT true,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Constraint: uma credencial por empresa+município
    UNIQUE(empresa_id, municipio_codigo)
);

-- Comentários descritivos
COMMENT ON TABLE credenciais_nfse IS 'Credenciais de acesso às APIs municipais de NFS-e';
COMMENT ON COLUMN credenciais_nfse.empresa_id IS 'UUID da empresa no Hi-Control';
COMMENT ON COLUMN credenciais_nfse.municipio_codigo IS 'Código IBGE do município (7 dígitos)';
COMMENT ON COLUMN credenciais_nfse.usuario IS 'Usuário/login para autenticação na API municipal';
COMMENT ON COLUMN credenciais_nfse.senha IS 'Senha para autenticação na API municipal';
COMMENT ON COLUMN credenciais_nfse.token IS 'Token de acesso direto (se a API aceitar)';
COMMENT ON COLUMN credenciais_nfse.cnpj IS 'CNPJ usado para contexto de autenticação';
COMMENT ON COLUMN credenciais_nfse.ativo IS 'Se a credencial está ativa para uso';


-- ============================================
-- 2. ÍNDICES PARA credenciais_nfse
-- ============================================

CREATE INDEX IF NOT EXISTS idx_credenciais_nfse_empresa
    ON credenciais_nfse(empresa_id);

CREATE INDEX IF NOT EXISTS idx_credenciais_nfse_municipio
    ON credenciais_nfse(municipio_codigo);

CREATE INDEX IF NOT EXISTS idx_credenciais_nfse_ativo
    ON credenciais_nfse(empresa_id, ativo)
    WHERE ativo = true;


-- ============================================
-- 3. TRIGGER DE UPDATED_AT
-- ============================================
-- Reutiliza a função update_updated_at_column()
-- que já deve existir no banco

-- Criar função se não existir
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Aplicar trigger
DROP TRIGGER IF EXISTS update_credenciais_nfse_updated_at ON credenciais_nfse;
CREATE TRIGGER update_credenciais_nfse_updated_at
    BEFORE UPDATE ON credenciais_nfse
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- ============================================
-- 4. EXPANDIR TABELA notas_fiscais PARA NFS-e
-- ============================================
-- Adicionar campos específicos de NFS-e que não
-- existem na estrutura original de NF-e

-- Campos de serviço (NFS-e)
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS municipio_codigo VARCHAR(7),
ADD COLUMN IF NOT EXISTS municipio_nome VARCHAR(100),
ADD COLUMN IF NOT EXISTS codigo_verificacao VARCHAR(100),
ADD COLUMN IF NOT EXISTS link_visualizacao TEXT,
ADD COLUMN IF NOT EXISTS descricao_servico TEXT,
ADD COLUMN IF NOT EXISTS codigo_servico VARCHAR(20),
ADD COLUMN IF NOT EXISTS valor_iss DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS aliquota_iss DECIMAL(5,4) DEFAULT 0;

-- Comentários nos novos campos
COMMENT ON COLUMN notas_fiscais.municipio_codigo IS 'Código IBGE do município (NFS-e)';
COMMENT ON COLUMN notas_fiscais.municipio_nome IS 'Nome do município emissor (NFS-e)';
COMMENT ON COLUMN notas_fiscais.codigo_verificacao IS 'Código de verificação/autenticidade (NFS-e)';
COMMENT ON COLUMN notas_fiscais.link_visualizacao IS 'URL para visualização da nota no portal municipal';
COMMENT ON COLUMN notas_fiscais.descricao_servico IS 'Descrição/discriminação do serviço prestado';
COMMENT ON COLUMN notas_fiscais.codigo_servico IS 'Código do serviço na lista municipal';
COMMENT ON COLUMN notas_fiscais.valor_iss IS 'Valor do ISS (NFS-e)';
COMMENT ON COLUMN notas_fiscais.aliquota_iss IS 'Alíquota do ISS (NFS-e)';


-- ============================================
-- 5. ÍNDICES PARA CAMPOS NFS-e
-- ============================================

CREATE INDEX IF NOT EXISTS idx_notas_fiscais_municipio
    ON notas_fiscais(municipio_codigo)
    WHERE municipio_codigo IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_notas_fiscais_tipo_nfse
    ON notas_fiscais(tipo_nf)
    WHERE tipo_nf = 'NFSE';

CREATE INDEX IF NOT EXISTS idx_notas_fiscais_codigo_verif
    ON notas_fiscais(codigo_verificacao)
    WHERE codigo_verificacao IS NOT NULL AND codigo_verificacao != '';


-- ============================================
-- 6. RLS (Row Level Security) PARA credenciais_nfse
-- ============================================

-- Habilitar RLS
ALTER TABLE credenciais_nfse ENABLE ROW LEVEL SECURITY;

-- Policy: Usuários só veem credenciais de suas empresas
CREATE POLICY credenciais_nfse_select_policy ON credenciais_nfse
    FOR SELECT
    USING (
        empresa_id IN (
            SELECT id FROM empresas 
            WHERE usuario_id = auth.uid()
        )
    );

-- Policy: Usuários só inserem credenciais para suas empresas
CREATE POLICY credenciais_nfse_insert_policy ON credenciais_nfse
    FOR INSERT
    WITH CHECK (
        empresa_id IN (
            SELECT id FROM empresas 
            WHERE usuario_id = auth.uid()
        )
    );

-- Policy: Usuários só atualizam credenciais de suas empresas
CREATE POLICY credenciais_nfse_update_policy ON credenciais_nfse
    FOR UPDATE
    USING (
        empresa_id IN (
            SELECT id FROM empresas 
            WHERE usuario_id = auth.uid()
        )
    );

-- Policy: Usuários só deletam credenciais de suas empresas
CREATE POLICY credenciais_nfse_delete_policy ON credenciais_nfse
    FOR DELETE
    USING (
        empresa_id IN (
            SELECT id FROM empresas 
            WHERE usuario_id = auth.uid()
        )
    );


-- ============================================
-- VERIFICAÇÃO
-- ============================================
-- Rode estas queries para verificar se tudo foi criado:
--
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'credenciais_nfse';
--
-- SELECT column_name, data_type 
-- FROM information_schema.columns 
-- WHERE table_name = 'notas_fiscais' 
-- AND column_name IN ('municipio_codigo', 'municipio_nome', 'codigo_verificacao', 
--                     'descricao_servico', 'codigo_servico', 'valor_iss', 'aliquota_iss');
