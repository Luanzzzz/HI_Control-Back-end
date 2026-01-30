#!/usr/bin/env python3
"""
Script para criar usuários parceiros da Hi-Control
Gera hash bcrypt e SQL INSERT para usuários de teste/parceiros

Uso:
    python scripts/create_partner_user.py --email socio.teste@hicontrol.com.br --password "HiControl@Partner2026" --name "Sócio Hi-Control (Teste)"
"""

import bcrypt
import argparse
import uuid
from datetime import datetime, timedelta


def generate_password_hash(password: str) -> str:
    """Gera hash bcrypt da senha (compatível com security.py)"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def generate_user_sql(
    email: str,
    password: str,
    nome_completo: str,
    plano: str = 'enterprise',
    user_uuid: str = None
) -> tuple[str, str, str]:
    """
    Gera SQL INSERT para usuário e assinatura
    
    Args:
        email: Email do usuário
        password: Senha em texto plano (será hasheada)
        nome_completo: Nome completo do usuário
        plano: Nome do plano ('basico', 'profissional', 'enterprise')
        user_uuid: UUID customizado (opcional, senão gera automaticamente)
    
    Returns:
        tuple: (user_id, password_hash, sql_insert)
    """
    # Gerar UUID se não fornecido
    user_id = user_uuid or str(uuid.uuid4())
    
    # Gerar hash da senha
    password_hash = generate_password_hash(password)
    
    # Data de término da assinatura (1 ano a partir de hoje)
    data_fim = (datetime.now() + timedelta(days=365)).strftime('%Y-%m-%d')
    
    # SQL para inserir usuário
    sql_usuario = f"""
-- Inserir usuário parceiro Hi-Control
INSERT INTO usuarios (id, email, nome_completo, hashed_password, ativo, email_verificado, auth_user_id, created_at)
VALUES (
    '{user_id}',
    '{email}',
    '{nome_completo}',
    '{password_hash}',
    true,
    true,
    NULL,
    NOW()
) ON CONFLICT (email) DO NOTHING;
"""
    
    # SQL para inserir assinatura
    sql_assinatura = f"""
-- Criar assinatura {plano} para usuário {email}
INSERT INTO assinaturas (usuario_id, plano_id, data_inicio, data_fim, status, tipo_cobranca, valor_pago)
SELECT
    '{user_id}',
    id,
    CURRENT_DATE,
    '{data_fim}'::DATE,
    'ativa',
    'anual',
    CASE
        WHEN nome = 'basico' THEN 970.00
        WHEN nome = 'profissional' THEN 1970.00
        WHEN nome = 'enterprise' THEN 4970.00
        ELSE 0.00
    END
FROM planos WHERE nome = '{plano}'
LIMIT 1
ON CONFLICT DO NOTHING;
"""
    
    # SQL completo
    sql_complete = sql_usuario + "\n" + sql_assinatura
    
    return user_id, password_hash, sql_complete


def main():
    parser = argparse.ArgumentParser(
        description='Criar usuário parceiro Hi-Control com hash bcrypt'
    )
    parser.add_argument(
        '--email',
        required=True,
        help='Email do usuário parceiro'
    )
    parser.add_argument(
        '--password',
        required=True,
        help='Senha do usuário (será hasheada)'
    )
    parser.add_argument(
        '--name',
        required=True,
        help='Nome completo do usuário'
    )
    parser.add_argument(
        '--plano',
        default='enterprise',
        choices=['basico', 'profissional', 'enterprise'],
        help='Plano de assinatura (padrão: enterprise)'
    )
    parser.add_argument(
        '--uuid',
        default=None,
        help='UUID customizado (opcional)'
    )
    parser.add_argument(
        '--output',
        default=None,
        help='Arquivo de saída para o SQL (opcional)'
    )
    
    args = parser.parse_args()
    
    # Gerar SQL
    user_id, password_hash, sql = generate_user_sql(
        email=args.email,
        password=args.password,
        nome_completo=args.name,
        plano=args.plano,
        user_uuid=args.uuid
    )
    
    # Exibir informações
    print("=" * 80)
    print("USUÁRIO PARCEIRO HI-CONTROL - GERADO COM SUCESSO")
    print("=" * 80)
    print(f"UUID:          {user_id}")
    print(f"Email:         {args.email}")
    print(f"Nome:          {args.name}")
    print(f"Plano:         {args.plano}")
    print(f"Senha Hash:    {password_hash[:50]}...")
    print("=" * 80)
    print("\nSQL PARA EXECUTAR NO SUPABASE:")
    print("=" * 80)
    print(sql)
    print("=" * 80)
    
    # Salvar em arquivo se especificado
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(f"-- Usuário Parceiro: {args.email}\n")
            f.write(f"-- Gerado em: {datetime.now().isoformat()}\n")
            f.write(f"-- UUID: {user_id}\n\n")
            f.write(sql)
        print(f"\n✅ SQL salvo em: {args.output}")
    
    print("\n🟢 CREDENCIAIS PARA REPASSAR AOS SÓCIOS:")
    print(f"   Email: {args.email}")
    print(f"   Senha: {args.password}")
    print("\n⚠️  IMPORTANTE: Execute o SQL acima no SQL Editor do Supabase")


if __name__ == "__main__":
    main()
