-- ============================================
-- HI-CONTROL - ADICIONAR municipio_codigo EM empresas
-- ============================================
-- Data: 2026-02-09
-- Versão: 004
-- Descrição: Adiciona campo municipio_codigo (IBGE) na tabela empresas
--            para suporte a NFS-e

-- ============================================
-- IMPORTANTE: Execute no SQL Editor do Supabase
-- Dashboard > SQL Editor > New Query
-- ============================================

-- Adicionar campo municipio_codigo na tabela empresas
ALTER TABLE empresas
ADD COLUMN IF NOT EXISTS municipio_codigo VARCHAR(7),
ADD COLUMN IF NOT EXISTS municipio_nome VARCHAR(100);

-- Comentários
COMMENT ON COLUMN empresas.municipio_codigo IS 'Código IBGE do município (7 dígitos) - usado para NFS-e';
COMMENT ON COLUMN empresas.municipio_nome IS 'Nome do município conforme IBGE';

-- Índice para busca rápida
CREATE INDEX IF NOT EXISTS idx_empresas_municipio_codigo
    ON empresas(municipio_codigo)
    WHERE municipio_codigo IS NOT NULL;

-- ============================================
-- ATUALIZAR MUNICÍPIOS CONHECIDOS (OPCIONAL)
-- ============================================
-- Você pode executar estas queries para popular automaticamente
-- os códigos IBGE baseado em cidade/estado conhecidos:

-- Belo Horizonte/MG
UPDATE empresas
SET municipio_codigo = '3106200',
    municipio_nome = 'Belo Horizonte'
WHERE cidade ILIKE '%belo horizonte%'
  AND estado = 'MG'
  AND municipio_codigo IS NULL;

-- São Paulo/SP
UPDATE empresas
SET municipio_codigo = '3550308',
    municipio_nome = 'São Paulo'
WHERE cidade ILIKE '%são paulo%'
  AND estado = 'SP'
  AND municipio_codigo IS NULL;

-- Rio de Janeiro/RJ
UPDATE empresas
SET municipio_codigo = '3304557',
    municipio_nome = 'Rio de Janeiro'
WHERE cidade ILIKE '%rio de janeiro%'
  AND estado = 'RJ'
  AND municipio_codigo IS NULL;

-- Curitiba/PR
UPDATE empresas
SET municipio_codigo = '4106902',
    municipio_nome = 'Curitiba'
WHERE cidade ILIKE '%curitiba%'
  AND estado = 'PR'
  AND municipio_codigo IS NULL;

-- Porto Alegre/RS
UPDATE empresas
SET municipio_codigo = '4314902',
    municipio_nome = 'Porto Alegre'
WHERE cidade ILIKE '%porto alegre%'
  AND estado = 'RS'
  AND municipio_codigo IS NULL;

-- ============================================
-- VERIFICAÇÃO
-- ============================================
-- Rode esta query para ver quantas empresas têm municipio_codigo:
--
-- SELECT 
--     COUNT(*) as total,
--     COUNT(municipio_codigo) as com_codigo,
--     COUNT(*) - COUNT(municipio_codigo) as sem_codigo
-- FROM empresas
-- WHERE deleted_at IS NULL;
