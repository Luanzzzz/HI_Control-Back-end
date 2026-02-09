-- ============================================
-- Migration 007: Suporte ao CT-e (Conhecimento de Transporte Eletrônico)
-- Modelo 57
-- ============================================

-- Tabela de CT-e emitidos
CREATE TABLE IF NOT EXISTS cte_emitidos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,
    numero_ct VARCHAR(9) NOT NULL,
    serie VARCHAR(3) DEFAULT '1',
    modelo VARCHAR(2) DEFAULT '57',
    chave_acesso VARCHAR(44),
    situacao VARCHAR(30) DEFAULT 'pendente',
    protocolo VARCHAR(20),
    
    -- Tipo
    tipo_cte VARCHAR(1) DEFAULT '0',  -- 0=Normal, 1=Complementar, 2=Anulação, 3=Substituto
    modal VARCHAR(2) DEFAULT '01',     -- 01=Rodoviário, 02=Aéreo, 03=Aquaviário, 04=Ferroviário, 05=Dutoviário
    tipo_servico VARCHAR(1) DEFAULT '0', -- 0=Normal, 1=Subcontratação, 2=Redespacho, 3=Redespacho Intermediário, 4=Serviço Vinculado Multimodal
    
    -- Remetente
    rem_cnpj VARCHAR(14),
    rem_cpf VARCHAR(11),
    rem_nome VARCHAR(100),
    rem_ie VARCHAR(20),
    rem_uf VARCHAR(2),
    rem_municipio VARCHAR(100),
    
    -- Destinatário
    dest_cnpj VARCHAR(14),
    dest_cpf VARCHAR(11),
    dest_nome VARCHAR(100),
    dest_ie VARCHAR(20),
    dest_uf VARCHAR(2),
    dest_municipio VARCHAR(100),
    
    -- Expedidor (opcional)
    exped_cnpj VARCHAR(14),
    exped_nome VARCHAR(100),
    
    -- Recebedor (opcional)
    receb_cnpj VARCHAR(14),
    receb_nome VARCHAR(100),
    
    -- Valores
    valor_total_servico DECIMAL(15,2) DEFAULT 0,
    valor_receber DECIMAL(15,2) DEFAULT 0,
    valor_icms DECIMAL(15,2) DEFAULT 0,
    valor_icms_st DECIMAL(15,2) DEFAULT 0,
    
    -- Carga
    valor_carga DECIMAL(15,2) DEFAULT 0,
    produto_predominante VARCHAR(120),
    quantidade_carga DECIMAL(15,4) DEFAULT 0,
    unidade_medida VARCHAR(5) DEFAULT 'KG',
    
    -- NF-e vinculadas
    nfe_vinculadas JSONB DEFAULT '[]',
    
    -- CFOP e natureza
    cfop VARCHAR(4),
    natureza_operacao VARCHAR(60),
    
    -- XML
    xml_completo TEXT,
    
    -- Datas
    data_emissao TIMESTAMPTZ,
    data_autorizacao TIMESTAMPTZ,
    ambiente VARCHAR(1) DEFAULT '2',
    
    -- Auditoria
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_cte_empresa ON cte_emitidos(empresa_id);
CREATE INDEX IF NOT EXISTS idx_cte_chave ON cte_emitidos(chave_acesso);
CREATE INDEX IF NOT EXISTS idx_cte_situacao ON cte_emitidos(situacao);
CREATE INDEX IF NOT EXISTS idx_cte_remetente ON cte_emitidos(rem_cnpj);
CREATE INDEX IF NOT EXISTS idx_cte_destinatario ON cte_emitidos(dest_cnpj);
CREATE INDEX IF NOT EXISTS idx_cte_data ON cte_emitidos(data_emissao DESC);

-- RLS
ALTER TABLE cte_emitidos ENABLE ROW LEVEL SECURITY;

CREATE POLICY "cte_select_policy" ON cte_emitidos
    FOR SELECT USING (
        empresa_id IN (SELECT id FROM empresas WHERE usuario_id = auth.uid())
    );

CREATE POLICY "cte_insert_policy" ON cte_emitidos
    FOR INSERT WITH CHECK (
        empresa_id IN (SELECT id FROM empresas WHERE usuario_id = auth.uid())
    );

CREATE POLICY "cte_update_policy" ON cte_emitidos
    FOR UPDATE USING (
        empresa_id IN (SELECT id FROM empresas WHERE usuario_id = auth.uid())
    );

-- Numeração CT-e na tabela genérica
-- (usa a mesma tabela numeracao_fiscal com modelo '57')

-- Adicionar campos de transporte à empresa se não existirem
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'empresas' AND column_name = 'rntrc') THEN
        ALTER TABLE empresas ADD COLUMN rntrc VARCHAR(20);
    END IF;
    
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'empresas' AND column_name = 'tipo_transportador') THEN
        ALTER TABLE empresas ADD COLUMN tipo_transportador VARCHAR(3);
        -- ETC=Empresa de Transporte Rodoviário, TAC=Transportador Autônomo, CTC=Cooperativa
    END IF;
END $$;
