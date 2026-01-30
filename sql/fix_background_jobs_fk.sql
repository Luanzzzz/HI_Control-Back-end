-- ============================================================================
-- MIGRATION: Fix Foreign Key Constraint for background_jobs
-- ============================================================================
-- Description: 
-- The 'background_jobs' table was created referencing 'auth.users' (Supabase Auth).
-- However, the application uses a custom 'public.usuarios' table for authentication.
-- This causes INSERT failures when the user exists in 'usuarios' but not 'auth.users'.
--
-- This script changes the Foreign Key to point to 'public.usuarios'.
-- ============================================================================

-- 1. Drop the existing inconsistent Foreign Key
ALTER TABLE background_jobs
DROP CONSTRAINT IF EXISTS background_jobs_user_id_fkey;

-- 2. Add the correct Foreign Key referencing public.usuarios
ALTER TABLE background_jobs
ADD CONSTRAINT background_jobs_user_id_fkey
FOREIGN KEY (user_id)
REFERENCES public.usuarios(id)
ON DELETE CASCADE; -- Optional: Delete jobs if user is deleted

-- 3. Verify (Optional comment)
-- SELECT * FROM information_schema.table_constraints WHERE table_name = 'background_jobs';
