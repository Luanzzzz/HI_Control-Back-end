-- Tabela para gerenciar Jobs de processamento em segundo plano (Polling)
create table if not exists background_jobs (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) not null,
  type text not null, -- 'nfe_distribuicao', etc.
  status text not null default 'pending', -- 'pending', 'processing', 'completed', 'failed'
  result jsonb, -- Resultado resumido (ex: {"total": 10, "nsu": 123})
  error text,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Índices para performance
create index if not exists idx_background_jobs_user_id on background_jobs(user_id);
create index if not exists idx_background_jobs_status on background_jobs(status);

-- Política RLS (Row Level Security)
alter table background_jobs enable row level security;

-- Usuários podem ver apenas seus próprios jobs
create policy "Users can view their own jobs"
  on background_jobs for select
  using (auth.uid() = user_id);

-- Backend (service_role) tem acesso total (implícito no Supabase admin client)
