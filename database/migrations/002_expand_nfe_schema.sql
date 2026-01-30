-- ============================================
-- HI-CONTROL - EXPANSÃO SCHEMA NF-e
-- ============================================
-- Data: 2026-01-26
-- Versão: 002
-- Baseado em: Auditoria PyNFe v1.0 + Plan

-- ============================================
-- IMPORTANTE: Execute no SQL Editor do Supabase
-- Dashboard > SQL Editor > New Query
-- ============================================

-- ============================================
-- 1. EXPANDIR TABELA notas_fiscais EXISTENTE
-- ============================================

-- Adicionar colunas para valores detalhados
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS valor_frete DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS valor_seguro DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS valor_desconto DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS valor_outras_despesas DECIMAL(15,2) DEFAULT 0;

-- Totais de impostos
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS total_icms DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_ipi DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_pis DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_cofins DECIMAL(15,2) DEFAULT 0,
ADD COLUMN IF NOT EXISTS total_iss DECIMAL(15,2) DEFAULT 0;

-- Dados do destinatário (pode ser CPF ou CNPJ)
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS destinatario_cpf VARCHAR(14),
ADD COLUMN IF NOT EXISTS destinatario_ie VARCHAR(20),
ADD COLUMN IF NOT EXISTS destinatario_uf VARCHAR(2);

-- Dados do emitente
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS emitente_uf VARCHAR(2),
ADD COLUMN IF NOT EXISTS emitente_ie VARCHAR(20);

-- Situação SEFAZ detalhada
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS situacao_sefaz_codigo VARCHAR(10),
ADD COLUMN IF NOT EXISTS situacao_sefaz_motivo TEXT;

-- Ambiente (produção/homologação)
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS ambiente VARCHAR(20) DEFAULT 'homologacao';

-- Informações adicionais da NF-e
ALTER TABLE notas_fiscais
ADD COLUMN IF NOT EXISTS informacoes_complementares TEXT,
ADD COLUMN IF NOT EXISTS informacoes_fisco TEXT;

-- Comentário sobre mudança
COMMENT ON COLUMN notas_fiscais.ambiente IS 'Ambiente SEFAZ: homologacao ou producao';
COMMENT ON COLUMN notas_fiscais.situacao_sefaz_codigo IS 'Código de retorno SEFAZ (100-999)';

-- ============================================
-- 2. CRIAR TABELA DE ITENS DA NOTA FISCAL
-- ============================================
CREATE TABLE IF NOT EXISTS nota_fiscal_itens (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nota_fiscal_id UUID NOT NULL REFERENCES notas_fiscais(id) ON DELETE CASCADE,

    -- Identificação do item (1-990)
    numero_item INTEGER NOT NULL CHECK (numero_item >= 1 AND numero_item <= 990),
    codigo_produto VARCHAR(60) NOT NULL,
    ean VARCHAR(14), -- Código de barras GTIN
    descricao VARCHAR(120) NOT NULL,

    -- Classificação fiscal
    ncm VARCHAR(8) NOT NULL, -- 8 dígitos obrigatórios
    cest VARCHAR(7), -- 7 dígitos (opcional, obrigatório para alguns produtos)
    cfop VARCHAR(4) NOT NULL, -- 4 dígitos
    unidade_comercial VARCHAR(6) NOT NULL, -- UN, KG, LT, etc

    -- Quantidades e valores comerciais
    quantidade_comercial DECIMAL(15,4) NOT NULL,
    valor_unitario_comercial DECIMAL(15,10) NOT NULL,
    valor_total_bruto DECIMAL(15,2) NOT NULL,
    valor_desconto DECIMAL(15,2) DEFAULT 0,
    valor_frete DECIMAL(15,2) DEFAULT 0,
    valor_seguro DECIMAL(15,2) DEFAULT 0,
    valor_outras_despesas DECIMAL(15,2) DEFAULT 0,

    -- ICMS (Imposto sobre Circulação de Mercadorias e Serviços)
    cst_icms VARCHAR(3), -- CST ou CSOSN
    origem_icms VARCHAR(1), -- 0-8 (0=Nacional, 1=Estrangeira Importação Direta, etc)
    modalidade_bc_icms INTEGER, -- 0-3 (modalidade determinação BC ICMS)
    base_calculo_icms DECIMAL(15,2) DEFAULT 0,
    aliquota_icms DECIMAL(5,2) DEFAULT 0,
    valor_icms DECIMAL(15,2) DEFAULT 0,

    -- ICMS ST (Substituição Tributária)
    modalidade_bc_icms_st INTEGER,
    base_calculo_icms_st DECIMAL(15,2) DEFAULT 0,
    aliquota_icms_st DECIMAL(5,2) DEFAULT 0,
    valor_icms_st DECIMAL(15,2) DEFAULT 0,

    -- IPI (Imposto sobre Produtos Industrializados)
    cst_ipi VARCHAR(2),
    base_calculo_ipi DECIMAL(15,2) DEFAULT 0,
    aliquota_ipi DECIMAL(5,2) DEFAULT 0,
    valor_ipi DECIMAL(15,2) DEFAULT 0,

    -- PIS (Programa de Integração Social)
    cst_pis VARCHAR(2),
    base_calculo_pis DECIMAL(15,2) DEFAULT 0,
    aliquota_pis DECIMAL(5,4) DEFAULT 0, -- 4 decimais para PIS
    valor_pis DECIMAL(15,2) DEFAULT 0,

    -- COFINS (Contribuição para Financiamento da Seguridade Social)
    cst_cofins VARCHAR(2),
    base_calculo_cofins DECIMAL(15,2) DEFAULT 0,
    aliquota_cofins DECIMAL(5,4) DEFAULT 0, -- 4 decimais para COFINS
    valor_cofins DECIMAL(15,2) DEFAULT 0,

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraint: garantir que item pertence a uma nota
    CONSTRAINT fk_nota_fiscal
        FOREIGN KEY (nota_fiscal_id)
        REFERENCES notas_fiscais(id)
        ON DELETE CASCADE,

    -- Constraint: número do item único dentro da nota
    CONSTRAINT unique_numero_item_por_nota
        UNIQUE (nota_fiscal_id, numero_item)
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_itens_nota ON nota_fiscal_itens(nota_fiscal_id);
CREATE INDEX IF NOT EXISTS idx_itens_ncm ON nota_fiscal_itens(ncm);
CREATE INDEX IF NOT EXISTS idx_itens_cfop ON nota_fiscal_itens(cfop);
CREATE INDEX IF NOT EXISTS idx_itens_codigo_produto ON nota_fiscal_itens(codigo_produto);

-- Comentários
COMMENT ON TABLE nota_fiscal_itens IS 'Itens (produtos/serviços) de cada nota fiscal com impostos detalhados';
COMMENT ON COLUMN nota_fiscal_itens.ncm IS 'Nomenclatura Comum do Mercosul - 8 dígitos obrigatórios';
COMMENT ON COLUMN nota_fiscal_itens.cfop IS 'Código Fiscal de Operações e Prestações - 4 dígitos';
COMMENT ON COLUMN nota_fiscal_itens.cst_icms IS 'Código de Situação Tributária do ICMS';

-- ============================================
-- 3. CRIAR TABELA DE TRANSPORTE
-- ============================================
CREATE TABLE IF NOT EXISTS nota_fiscal_transporte (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nota_fiscal_id UUID UNIQUE NOT NULL REFERENCES notas_fiscais(id) ON DELETE CASCADE,

    -- Modalidade de frete:
    -- 0 = Contratação do Frete por conta do Remetente (CIF)
    -- 1 = Contratação do Frete por conta do Destinatário (FOB)
    -- 2 = Contratação do Frete por conta de Terceiros
    -- 9 = Sem Ocorrência de Transporte
    modalidade_frete INTEGER NOT NULL CHECK (modalidade_frete IN (0,1,2,9)),

    -- Dados da transportadora (CNPJ ou CPF)
    transportadora_cnpj VARCHAR(18),
    transportadora_cpf VARCHAR(14),
    transportadora_razao_social VARCHAR(255),
    transportadora_ie VARCHAR(20),
    transportadora_endereco TEXT,
    transportadora_municipio VARCHAR(100),
    transportadora_uf VARCHAR(2),

    -- Dados do veículo
    placa_veiculo VARCHAR(8), -- Suporta formato antigo (AAA9999) e Mercosul (AAA9A99)
    uf_veiculo VARCHAR(2),
    rntc VARCHAR(20), -- Registro Nacional de Transportador de Carga

    -- Volumes transportados
    quantidade_volumes INTEGER CHECK (quantidade_volumes >= 0),
    especie_volumes VARCHAR(60), -- Ex: "Caixa", "Pallet", "Embalagem"
    marca_volumes VARCHAR(60),
    numeracao_volumes VARCHAR(60),
    peso_liquido DECIMAL(15,3), -- em kg, 3 decimais
    peso_bruto DECIMAL(15,3), -- em kg, 3 decimais

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraint: garantir que transporte pertence a uma nota
    CONSTRAINT fk_nota_transporte
        FOREIGN KEY (nota_fiscal_id)
        REFERENCES notas_fiscais(id)
        ON DELETE CASCADE
);

-- Índice
CREATE INDEX IF NOT EXISTS idx_transporte_nota ON nota_fiscal_transporte(nota_fiscal_id);

-- Comentários
COMMENT ON TABLE nota_fiscal_transporte IS 'Dados de transporte e frete da NF-e';
COMMENT ON COLUMN nota_fiscal_transporte.modalidade_frete IS '0=CIF, 1=FOB, 2=Terceiros, 9=Sem frete';
COMMENT ON COLUMN nota_fiscal_transporte.rntc IS 'Registro Nacional de Transportador de Carga';

-- ============================================
-- 4. CRIAR TABELA DE DUPLICATAS (COBRANÇA)
-- ============================================
CREATE TABLE IF NOT EXISTS nota_fiscal_duplicatas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nota_fiscal_id UUID NOT NULL REFERENCES notas_fiscais(id) ON DELETE CASCADE,

    -- Dados da duplicata
    numero_duplicata VARCHAR(60) NOT NULL,
    data_vencimento DATE NOT NULL,
    valor DECIMAL(15,2) NOT NULL CHECK (valor > 0),

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraint: garantir que duplicata pertence a uma nota
    CONSTRAINT fk_nota_duplicata
        FOREIGN KEY (nota_fiscal_id)
        REFERENCES notas_fiscais(id)
        ON DELETE CASCADE,

    -- Constraint: número da duplicata único dentro da nota
    CONSTRAINT unique_numero_duplicata_por_nota
        UNIQUE (nota_fiscal_id, numero_duplicata)
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_duplicatas_nota ON nota_fiscal_duplicatas(nota_fiscal_id);
CREATE INDEX IF NOT EXISTS idx_duplicatas_vencimento ON nota_fiscal_duplicatas(data_vencimento);

-- Comentários
COMMENT ON TABLE nota_fiscal_duplicatas IS 'Duplicatas/parcelas de cobrança da NF-e';
COMMENT ON COLUMN nota_fiscal_duplicatas.numero_duplicata IS 'Número da parcela (ex: 001/003)';

-- ============================================
-- 5. CRIAR TABELA DE LOG DE COMUNICAÇÃO SEFAZ
-- ============================================
CREATE TABLE IF NOT EXISTS sefaz_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nota_fiscal_id UUID REFERENCES notas_fiscais(id) ON DELETE SET NULL,
    empresa_id UUID NOT NULL REFERENCES empresas(id) ON DELETE CASCADE,

    -- Identificação da operação
    operacao VARCHAR(50) NOT NULL, -- 'autorizacao', 'consulta', 'cancelamento', 'inutilizacao'
    uf VARCHAR(2) NOT NULL, -- Estado do SEFAZ consultado
    ambiente VARCHAR(20) NOT NULL DEFAULT 'homologacao', -- 'producao' ou 'homologacao'

    -- Request enviado
    request_xml TEXT,
    request_timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Response recebido
    response_xml TEXT,
    response_timestamp TIMESTAMP WITH TIME ZONE,

    -- Status da resposta
    status_codigo VARCHAR(10), -- Código de retorno SEFAZ (100, 101, 204, etc)
    status_descricao TEXT,
    protocolo VARCHAR(50), -- Número do protocolo de autorização

    -- Resultado
    sucesso BOOLEAN DEFAULT false,
    mensagem_erro TEXT,

    -- Metadata de performance
    tempo_resposta_ms INTEGER, -- Tempo de resposta em milissegundos
    ip_sefaz VARCHAR(45), -- IP do servidor SEFAZ que respondeu

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Constraints
    CONSTRAINT fk_sefaz_log_empresa
        FOREIGN KEY (empresa_id)
        REFERENCES empresas(id)
        ON DELETE CASCADE
);

-- Índices para consultas e relatórios
CREATE INDEX IF NOT EXISTS idx_sefaz_log_nota ON sefaz_log(nota_fiscal_id);
CREATE INDEX IF NOT EXISTS idx_sefaz_log_empresa ON sefaz_log(empresa_id);
CREATE INDEX IF NOT EXISTS idx_sefaz_log_operacao ON sefaz_log(operacao);
CREATE INDEX IF NOT EXISTS idx_sefaz_log_data ON sefaz_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sefaz_log_sucesso ON sefaz_log(sucesso);
CREATE INDEX IF NOT EXISTS idx_sefaz_log_ambiente ON sefaz_log(ambiente);

-- Comentários
COMMENT ON TABLE sefaz_log IS 'Registro de todas as comunicações com SEFAZ para auditoria';
COMMENT ON COLUMN sefaz_log.operacao IS 'Tipo: autorizacao, consulta, cancelamento, inutilizacao';
COMMENT ON COLUMN sefaz_log.status_codigo IS 'Código SEFAZ: 100=Autorizado, 101=Cancelado, 204=Duplicado, etc';
COMMENT ON COLUMN sefaz_log.tempo_resposta_ms IS 'Tempo de resposta do SEFAZ em milissegundos';

-- ============================================
-- 6. ATUALIZAR TRIGGER updated_at PARA NOVAS TABELAS
-- ============================================

-- Trigger para nota_fiscal_itens
CREATE TRIGGER update_itens_updated_at
    BEFORE UPDATE ON nota_fiscal_itens
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger para nota_fiscal_transporte
CREATE TRIGGER update_transporte_updated_at
    BEFORE UPDATE ON nota_fiscal_transporte
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger para nota_fiscal_duplicatas
CREATE TRIGGER update_duplicatas_updated_at
    BEFORE UPDATE ON nota_fiscal_duplicatas
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 7. FUNÇÃO PARA CALCULAR TOTAIS AUTOMATICAMENTE
-- ============================================
CREATE OR REPLACE FUNCTION calcular_totais_nota()
RETURNS TRIGGER AS $$
BEGIN
    -- Atualiza valores totais baseado nos itens
    UPDATE notas_fiscais
    SET
        valor_produtos = (
            SELECT COALESCE(SUM(valor_total_bruto - COALESCE(valor_desconto, 0)), 0)
            FROM nota_fiscal_itens
            WHERE nota_fiscal_id = NEW.nota_fiscal_id
        ),
        total_icms = (
            SELECT COALESCE(SUM(valor_icms), 0)
            FROM nota_fiscal_itens
            WHERE nota_fiscal_id = NEW.nota_fiscal_id
        ),
        total_ipi = (
            SELECT COALESCE(SUM(valor_ipi), 0)
            FROM nota_fiscal_itens
            WHERE nota_fiscal_id = NEW.nota_fiscal_id
        ),
        total_pis = (
            SELECT COALESCE(SUM(valor_pis), 0)
            FROM nota_fiscal_itens
            WHERE nota_fiscal_id = NEW.nota_fiscal_id
        ),
        total_cofins = (
            SELECT COALESCE(SUM(valor_cofins), 0)
            FROM nota_fiscal_itens
            WHERE nota_fiscal_id = NEW.nota_fiscal_id
        ),
        updated_at = NOW()
    WHERE id = NEW.nota_fiscal_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger para recalcular totais quando itens mudam
CREATE TRIGGER trigger_calcular_totais
    AFTER INSERT OR UPDATE OR DELETE ON nota_fiscal_itens
    FOR EACH ROW
    EXECUTE FUNCTION calcular_totais_nota();

-- ============================================
-- 8. ATIVAR RLS (ROW LEVEL SECURITY) NAS NOVAS TABELAS
-- ============================================

ALTER TABLE nota_fiscal_itens ENABLE ROW LEVEL SECURITY;
ALTER TABLE nota_fiscal_transporte ENABLE ROW LEVEL SECURITY;
ALTER TABLE nota_fiscal_duplicatas ENABLE ROW LEVEL SECURITY;
ALTER TABLE sefaz_log ENABLE ROW LEVEL SECURITY;

-- ============================================
-- 9. CRIAR POLÍTICAS RLS
-- ============================================

-- Política para nota_fiscal_itens
DROP POLICY IF EXISTS "Usuários veem itens de suas notas" ON nota_fiscal_itens;
CREATE POLICY "Usuários veem itens de suas notas"
    ON nota_fiscal_itens FOR ALL
    USING (nota_fiscal_id IN (
        SELECT nf.id FROM notas_fiscais nf
        JOIN empresas e ON nf.empresa_id = e.id
        JOIN usuarios u ON e.usuario_id = u.id
        WHERE u.auth_user_id = auth.uid()
    ));

-- Política para nota_fiscal_transporte
DROP POLICY IF EXISTS "Usuários veem transporte de suas notas" ON nota_fiscal_transporte;
CREATE POLICY "Usuários veem transporte de suas notas"
    ON nota_fiscal_transporte FOR ALL
    USING (nota_fiscal_id IN (
        SELECT nf.id FROM notas_fiscais nf
        JOIN empresas e ON nf.empresa_id = e.id
        JOIN usuarios u ON e.usuario_id = u.id
        WHERE u.auth_user_id = auth.uid()
    ));

-- Política para nota_fiscal_duplicatas
DROP POLICY IF EXISTS "Usuários veem duplicatas de suas notas" ON nota_fiscal_duplicatas;
CREATE POLICY "Usuários veem duplicatas de suas notas"
    ON nota_fiscal_duplicatas FOR ALL
    USING (nota_fiscal_id IN (
        SELECT nf.id FROM notas_fiscais nf
        JOIN empresas e ON nf.empresa_id = e.id
        JOIN usuarios u ON e.usuario_id = u.id
        WHERE u.auth_user_id = auth.uid()
    ));

-- Política para sefaz_log (apenas leitura)
DROP POLICY IF EXISTS "Usuários veem logs de suas empresas" ON sefaz_log;
CREATE POLICY "Usuários veem logs de suas empresas"
    ON sefaz_log FOR SELECT
    USING (empresa_id IN (
        SELECT e.id FROM empresas e
        JOIN usuarios u ON e.usuario_id = u.id
        WHERE u.auth_user_id = auth.uid()
    ));

-- ============================================
-- 10. VALIDAÇÃO FINAL
-- ============================================

-- Verificar se todas as tabelas foram criadas
DO $$
DECLARE
    tabelas_esperadas TEXT[] := ARRAY[
        'nota_fiscal_itens',
        'nota_fiscal_transporte',
        'nota_fiscal_duplicatas',
        'sefaz_log'
    ];
    tabela TEXT;
    tabela_existe BOOLEAN;
BEGIN
    FOREACH tabela IN ARRAY tabelas_esperadas
    LOOP
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name = tabela
        ) INTO tabela_existe;

        IF tabela_existe THEN
            RAISE NOTICE '✅ Tabela % criada com sucesso', tabela;
        ELSE
            RAISE EXCEPTION '❌ ERRO: Tabela % não foi criada', tabela;
        END IF;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
    RAISE NOTICE '✅ MIGRAÇÃO 002 CONCLUÍDA COM SUCESSO';
    RAISE NOTICE '═══════════════════════════════════════════════════════════';
    RAISE NOTICE '';
    RAISE NOTICE 'Próximos passos:';
    RAISE NOTICE '1. Implementar modelos Pydantic (nfe_completa.py)';
    RAISE NOTICE '2. Criar serviços SEFAZ';
    RAISE NOTICE '3. Adicionar endpoints de emissão';
    RAISE NOTICE '';
END $$;
