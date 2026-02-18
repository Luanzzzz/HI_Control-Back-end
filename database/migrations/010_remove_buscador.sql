-- ============================================
-- MIGRATION: Remocao do modulo de buscador
-- ============================================

-- Funcoes auxiliares do cache/historico do buscador
DROP FUNCTION IF EXISTS limpar_cache_expirado();
DROP FUNCTION IF EXISTS limpar_historico_antigo();

-- Tabelas de cache/historico do buscador
DROP TABLE IF EXISTS cache_notas_fiscais CASCADE;
DROP TABLE IF EXISTS historico_consultas CASCADE;
