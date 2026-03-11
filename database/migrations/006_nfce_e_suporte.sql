-- ============================================
-- Migration 006: NFC-e + tabelas de suporte para interface de emissão
-- ============================================

-- Campos CSC (Código de Segurança do Contribuinte) para NFC-e
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'empresas' AND column_name = 'csc_id'
    ) THEN
        ALTER TABLE empresas ADD COLUMN csc_id TEXT;
        ALTER TABLE empresas ADD COLUMN csc_token TEXT;
    END IF;
END $$;

-- Tabela de produtos cadastrados
CREATE TABLE IF NOT EXISTS produtos_cadastrados (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    codigo TEXT NOT NULL,
    descricao TEXT NOT NULL,
    ncm TEXT,
    cfop TEXT,
    unidade TEXT DEFAULT 'UN',
    valor_unitario NUMERIC(15,4),
    cest TEXT,
    origem TEXT DEFAULT '0',
    cst_icms TEXT,
    cst_pis TEXT,
    cst_cofins TEXT,
    ativo BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(empresa_id, codigo)
);

-- Tabela CFOP
CREATE TABLE IF NOT EXISTS cfop_tabela (
    codigo TEXT PRIMARY KEY,
    descricao TEXT NOT NULL,
    tipo TEXT CHECK (tipo IN ('entrada', 'saida')),
    aplicacao TEXT
);

-- Tabela NCM
CREATE TABLE IF NOT EXISTS ncm_tabela (
    codigo TEXT PRIMARY KEY,
    descricao TEXT NOT NULL,
    capitulo TEXT,
    aliquota_ipi NUMERIC(5,2)
);

-- Tabela de numeração de NF-e/NFC-e
CREATE TABLE IF NOT EXISTS numeracao_fiscal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    modelo TEXT NOT NULL CHECK (modelo IN ('55', '65', '57')),
    serie TEXT NOT NULL DEFAULT '1',
    ultimo_numero INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(empresa_id, modelo, serie)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_produtos_empresa ON produtos_cadastrados(empresa_id);
CREATE INDEX IF NOT EXISTS idx_produtos_codigo ON produtos_cadastrados(empresa_id, codigo);
CREATE INDEX IF NOT EXISTS idx_produtos_ncm ON produtos_cadastrados(ncm);
CREATE INDEX IF NOT EXISTS idx_cfop_tipo ON cfop_tabela(tipo);
CREATE INDEX IF NOT EXISTS idx_ncm_capitulo ON ncm_tabela(capitulo);
CREATE INDEX IF NOT EXISTS idx_numeracao_empresa ON numeracao_fiscal(empresa_id, modelo, serie);

-- RLS
ALTER TABLE produtos_cadastrados ENABLE ROW LEVEL SECURITY;
ALTER TABLE numeracao_fiscal ENABLE ROW LEVEL SECURITY;

-- CFOPs básicos de saída (exemplos comuns)
INSERT INTO cfop_tabela (codigo, descricao, tipo, aplicacao) VALUES
    ('5101', 'Venda de produção do estabelecimento', 'saida', 'Operação interna'),
    ('5102', 'Venda de mercadoria adquirida ou recebida de terceiros', 'saida', 'Operação interna'),
    ('5405', 'Venda de mercadoria adquirida com ST (consumidor final)', 'saida', 'Operação interna'),
    ('5933', 'Prestação de serviço tributado pelo ISSQN', 'saida', 'Serviço'),
    ('6101', 'Venda de produção do estabelecimento (interestadual)', 'saida', 'Operação interestadual'),
    ('6102', 'Venda de mercadoria adquirida (interestadual)', 'saida', 'Operação interestadual'),
    ('1101', 'Compra para industrialização ou produção rural', 'entrada', 'Operação interna'),
    ('1102', 'Compra para comercialização', 'entrada', 'Operação interna'),
    ('2101', 'Compra para industrialização (interestadual)', 'entrada', 'Operação interestadual'),
    ('2102', 'Compra para comercialização (interestadual)', 'entrada', 'Operação interestadual'),
    ('5929', 'Lançamento efetuado em decorrência de emissão de NF de serviço', 'saida', 'NFS-e'),
    ('5949', 'Outra saída de mercadoria não especificada', 'saida', 'Outras')
ON CONFLICT (codigo) DO NOTHING;

-- Trigger updated_at
CREATE OR REPLACE TRIGGER update_produtos_updated_at
    BEFORE UPDATE ON produtos_cadastrados
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_numeracao_updated_at
    BEFORE UPDATE ON numeracao_fiscal
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
