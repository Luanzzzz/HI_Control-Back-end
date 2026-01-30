-- Migration to add certificate fields to empresas table
-- Should be applied to Supabase

ALTER TABLE empresas 
ADD COLUMN IF NOT EXISTS certificado_a1 TEXT, -- Store encrypted base64 string
ADD COLUMN IF NOT EXISTS certificado_validade DATE,
ADD COLUMN IF NOT EXISTS certificado_titular VARCHAR(255),
ADD COLUMN IF NOT EXISTS certificado_emissor VARCHAR(255);

-- Create index for validity check
CREATE INDEX IF NOT EXISTS idx_empresas_certificado_validade ON empresas(certificado_validade);
