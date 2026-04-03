-- ============================================
-- HI-CONTROL - SCHEMA SUPABASE
-- ============================================
-- Execute este script no SQL Editor do Supabase
-- Dashboard > SQL Editor > New Query

-- ============================================
-- 1. TABELA DE USUÁRIOS
-- ============================================
CREATE TABLE IF NOT EXISTS usuarios (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    nome_completo VARCHAR(255) NOT NULL,
    cpf VARCHAR(14) UNIQUE,
    telefone VARCHAR(20),
    avatar_url TEXT,

    -- Autenticação (integra com Supabase Auth)
    auth_user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Senha hash (para auth customizada sem Supabase Auth)
    hashed_password TEXT,

    -- Status
    ativo BOOLEAN DEFAULT true,
    email_verificado BOOLEAN DEFAULT false,

    -- Dados da Firma de Contabilidade
    razao_social_contador VARCHAR(255),
    cnpj_contador VARCHAR(18),
    inscricao_estadual_contador VARCHAR(50),
    logo_url_contador TEXT,

    -- Certificado Digital do Contador (A1)
    certificado_contador_a1 TEXT,
    certificado_contador_validade DATE,
    certificado_contador_titular TEXT,
    certificado_contador_emissor TEXT,

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios(email);
CREATE INDEX IF NOT EXISTS idx_usuarios_auth_user_id ON usuarios(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_ativo ON usuarios(ativo) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_usuarios_cnpj_contador ON usuarios(cnpj_contador) WHERE cnpj_contador IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_usuarios_cert_validade ON usuarios(certificado_contador_validade) WHERE certificado_contador_validade IS NOT NULL;

-- ============================================
-- 2. TABELA DE PLANOS
-- ============================================
CREATE TABLE IF NOT EXISTS planos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nome VARCHAR(100) NOT NULL, -- 'basico', 'profissional', 'enterprise'
    descricao TEXT,
    preco_mensal DECIMAL(10,2) NOT NULL,
    preco_anual DECIMAL(10,2),

    -- Limites do plano
    max_usuarios INTEGER DEFAULT 1,
    max_empresas INTEGER DEFAULT 1,
    max_notas_mes INTEGER DEFAULT 100,

    -- Módulos inclusos (JSON array de strings)
    modulos_disponiveis JSONB DEFAULT '[]'::jsonb,
    -- Exemplo: ["dashboard", "buscador_notas", "tarefas", "whatsapp"]

    -- Recursos adicionais
    possui_api BOOLEAN DEFAULT false,
    possui_whatsapp BOOLEAN DEFAULT false,
    possui_relatorios_avancados BOOLEAN DEFAULT false,

    -- Status
    ativo BOOLEAN DEFAULT true,

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Inserir planos padrão
INSERT INTO planos (nome, descricao, preco_mensal, preco_anual, modulos_disponiveis, max_empresas, max_notas_mes)
VALUES
    (
        'basico',
        'Plano básico para pequenos escritórios',
        97.00,
        970.00,
        '["dashboard", "buscador_notas", "tarefas"]'::jsonb,
        3,
        500
    ),
    (
        'profissional',
        'Plano completo para escritórios em crescimento',
        197.00,
        1970.00,
        '["dashboard", "buscador_notas", "emissor_notas", "tarefas", "whatsapp", "clientes", "estoque", "faturamento"]'::jsonb,
        10,
        2000
    ),
    (
        'enterprise',
        'Plano ilimitado para grandes operações',
        497.00,
        4970.00,
        '["dashboard", "buscador_notas", "emissor_notas", "tarefas", "whatsapp", "clientes", "estoque", "faturamento", "servicos", "financeiro", "agenda_medica"]'::jsonb,
        999,
        99999
    )
ON CONFLICT DO NOTHING;

-- ============================================
-- 3. TABELA DE ASSINATURAS
-- ============================================
CREATE TABLE IF NOT EXISTS assinaturas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id) ON DELETE CASCADE,
    plano_id UUID REFERENCES planos(id),

    -- Período
    data_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    data_fim DATE NOT NULL,
    tipo_cobranca VARCHAR(20) DEFAULT 'mensal', -- 'mensal' ou 'anual'

    -- Status
    status VARCHAR(50) DEFAULT 'ativa', -- 'ativa', 'cancelada', 'suspensa', 'trial'

    -- Pagamento
    valor_pago DECIMAL(10,2),
    metodo_pagamento VARCHAR(50), -- 'cartao', 'boleto', 'pix'
    gateway_pagamento_id VARCHAR(255), -- ID externo (Stripe, Mercado Pago, etc)

    -- Trial
    em_trial BOOLEAN DEFAULT false,
    trial_termina_em DATE,

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    cancelada_em TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_assinaturas_usuario ON assinaturas(usuario_id);
CREATE INDEX IF NOT EXISTS idx_assinaturas_status ON assinaturas(status);

-- ============================================
-- 4. TABELA DE EMPRESAS (Clientes dos Contadores)
-- ============================================
CREATE TABLE IF NOT EXISTS empresas (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    usuario_id UUID REFERENCES usuarios(id) ON DELETE CASCADE,

    -- Dados cadastrais
    razao_social VARCHAR(255) NOT NULL,
    nome_fantasia VARCHAR(255),
    cnpj VARCHAR(18) UNIQUE NOT NULL,
    inscricao_estadual VARCHAR(50),
    inscricao_municipal VARCHAR(50),

    -- Endereço
    cep VARCHAR(10),
    logradouro VARCHAR(255),
    numero VARCHAR(20),
    complemento VARCHAR(100),
    bairro VARCHAR(100),
    cidade VARCHAR(100),
    estado VARCHAR(2),

    -- Contato
    email VARCHAR(255),
    telefone VARCHAR(20),

    -- Regime tributário
    regime_tributario VARCHAR(50), -- 'simples_nacional', 'lucro_presumido', 'lucro_real'

    -- Certificado Digital
    certificado_a1 TEXT, -- Base64 do certificado (criptografado)
    certificado_senha_hash TEXT,
    certificado_validade DATE,
    certificado_titular TEXT,
    certificado_emissor TEXT,

    -- Status
    ativa BOOLEAN DEFAULT true,

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_empresas_usuario ON empresas(usuario_id);
CREATE INDEX IF NOT EXISTS idx_empresas_cnpj ON empresas(cnpj);

-- ============================================
-- 5. TABELA DE NOTAS FISCAIS (MOCK - Futuramente PostgreSQL)
-- ============================================
CREATE TABLE IF NOT EXISTS notas_fiscais (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    empresa_id UUID REFERENCES empresas(id) ON DELETE CASCADE,

    -- Identificação
    numero_nf VARCHAR(20) NOT NULL,
    serie VARCHAR(10) NOT NULL,
    tipo_nf VARCHAR(10) NOT NULL, -- 'NFe', 'NFSe', 'NFCe', 'CTe'
    modelo VARCHAR(5), -- '55' (NFe), '65' (NFCe), '57' (CTe)

    -- Chave de acesso (44 dígitos)
    chave_acesso VARCHAR(44) UNIQUE,

    -- Datas
    data_emissao TIMESTAMP WITH TIME ZONE NOT NULL,
    data_autorizacao TIMESTAMP WITH TIME ZONE,

    -- Valores
    valor_total DECIMAL(15,2) NOT NULL,
    valor_produtos DECIMAL(15,2),
    valor_servicos DECIMAL(15,2),
    valor_icms DECIMAL(15,2),
    valor_ipi DECIMAL(15,2),
    valor_pis DECIMAL(15,2),
    valor_cofins DECIMAL(15,2),

    -- Partes
    cnpj_emitente VARCHAR(18) NOT NULL,
    nome_emitente VARCHAR(255),
    cnpj_destinatario VARCHAR(18),
    nome_destinatario VARCHAR(255),

    -- Status
    situacao VARCHAR(50) DEFAULT 'processando',
    -- 'processando', 'autorizada', 'cancelada', 'denegada', 'rejeitada'

    protocolo VARCHAR(50),
    motivo_cancelamento TEXT,

    -- Arquivos
    xml_url TEXT, -- URL do XML no Supabase Storage
    pdf_url TEXT, -- URL do DANFE

    -- Metadados
    observacoes TEXT,
    tags JSONB DEFAULT '[]'::jsonb,

    -- Auditoria
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_notas_empresa ON notas_fiscais(empresa_id);
CREATE INDEX IF NOT EXISTS idx_notas_chave ON notas_fiscais(chave_acesso);
CREATE INDEX IF NOT EXISTS idx_notas_tipo ON notas_fiscais(tipo_nf);
CREATE INDEX IF NOT EXISTS idx_notas_situacao ON notas_fiscais(situacao);
CREATE INDEX IF NOT EXISTS idx_notas_emissao ON notas_fiscais(data_emissao DESC);
CREATE INDEX IF NOT EXISTS idx_notas_cnpj_emitente ON notas_fiscais(cnpj_emitente);

-- ============================================
-- 6. ROW LEVEL SECURITY (RLS)
-- ============================================
-- Ativar RLS em todas as tabelas
ALTER TABLE usuarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE empresas ENABLE ROW LEVEL SECURITY;
ALTER TABLE assinaturas ENABLE ROW LEVEL SECURITY;
ALTER TABLE notas_fiscais ENABLE ROW LEVEL SECURITY;

-- Políticas: Usuário pode ver apenas seus próprios dados
CREATE POLICY "Usuários podem ver próprios dados"
    ON usuarios FOR SELECT
    USING (auth.uid() = auth_user_id);

CREATE POLICY "Usuários podem atualizar próprios dados"
    ON usuarios FOR UPDATE
    USING (auth.uid() = auth_user_id);

CREATE POLICY "Usuários podem ver próprias empresas"
    ON empresas FOR ALL
    USING (usuario_id IN (
        SELECT id FROM usuarios WHERE auth_user_id = auth.uid()
    ));

CREATE POLICY "Usuários podem ver próprias notas"
    ON notas_fiscais FOR ALL
    USING (empresa_id IN (
        SELECT id FROM empresas WHERE usuario_id IN (
            SELECT id FROM usuarios WHERE auth_user_id = auth.uid()
        )
    ));

-- ============================================
-- 7. TRIGGERS PARA UPDATED_AT
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_usuarios_updated_at
    BEFORE UPDATE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_empresas_updated_at
    BEFORE UPDATE ON empresas
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_notas_updated_at
    BEFORE UPDATE ON notas_fiscais
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 8. FUNÇÕES ÚTEIS
-- ============================================
-- Função para verificar se usuário tem acesso ao módulo
CREATE OR REPLACE FUNCTION usuario_tem_acesso_modulo(
    p_usuario_id UUID,
    p_modulo TEXT
)
RETURNS BOOLEAN AS $$
DECLARE
    v_tem_acesso BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1
        FROM assinaturas a
        JOIN planos p ON a.plano_id = p.id
        WHERE a.usuario_id = p_usuario_id
        AND a.status = 'ativa'
        AND a.data_fim >= CURRENT_DATE
        AND p.modulos_disponiveis @> to_jsonb(ARRAY[p_modulo])
    ) INTO v_tem_acesso;

    RETURN v_tem_acesso;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- 9. DADOS OPCIONAIS DE DESENVOLVIMENTO
-- ============================================
-- Não versionar credenciais reais ou senhas conhecidas neste schema.
-- Se precisar popular ambiente local, use scripts/seeds separados fora do schema base.

-- Seeds de desenvolvimento intencionais devem viver fora deste schema base.

-- ============================================
-- FIM DO SCHEMA
-- ============================================
