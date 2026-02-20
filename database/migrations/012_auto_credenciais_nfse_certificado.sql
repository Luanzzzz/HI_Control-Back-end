-- ============================================================
-- HI-CONTROL - Migration 012: Auto credenciais NFS-e por certificado
-- ============================================================
-- Objetivo:
-- 1) Criar/atualizar credenciais tecnicas NFS-e para empresas com A1
-- 2) Permitir fallback automatico por certificado no Sistema Nacional

INSERT INTO credenciais_nfse (
    empresa_id,
    municipio_codigo,
    usuario,
    senha,
    token,
    cnpj,
    ativo
)
SELECT
    e.id AS empresa_id,
    COALESCE(NULLIF(e.municipio_codigo, ''), '0000000') AS municipio_codigo,
    'AUTO_CERT_A1' AS usuario,
    NULL AS senha,
    'AUTO_CERT_A1' AS token,
    NULLIF(REGEXP_REPLACE(COALESCE(e.cnpj, ''), '\D', '', 'g'), '') AS cnpj,
    TRUE AS ativo
FROM empresas e
WHERE e.deleted_at IS NULL
  AND e.ativa = TRUE
  AND e.certificado_a1 IS NOT NULL
  AND e.certificado_senha_encrypted IS NOT NULL
ON CONFLICT (empresa_id, municipio_codigo)
DO UPDATE SET
    usuario = EXCLUDED.usuario,
    senha = EXCLUDED.senha,
    token = EXCLUDED.token,
    cnpj = EXCLUDED.cnpj,
    ativo = TRUE,
    updated_at = NOW();

