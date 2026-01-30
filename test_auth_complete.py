"""
Teste completo do fluxo de autenticacao
"""
import bcrypt
from supabase import create_client, Client
import os
from dotenv import load_dotenv

load_dotenv()

# Configuracao Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("=" * 60)
print("TESTE COMPLETO DE AUTENTICACAO")
print("=" * 60)

# 1. Conectar ao Supabase
print("\n1. Conectando ao Supabase...")
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("   [OK] Conectado com sucesso")
except Exception as e:
    print(f"   [ERRO] Erro ao conectar: {e}")
    exit(1)

# 2. Buscar usuario no banco
email = "luan.valentino78@gmail.com"
print(f"\n2. Buscando usuario: {email}")
try:
    response = supabase.table("usuarios")\
        .select("*")\
        .eq("email", email)\
        .single()\
        .execute()

    if response.data:
        user = response.data
        print(f"   [OK] Usuario encontrado")
        print(f"   - ID: {user['id']}")
        print(f"   - Email: {user['email']}")
        print(f"   - Nome: {user['nome_completo']}")
        print(f"   - Ativo: {user['ativo']}")
        print(f"   - Hash no banco: {user['hashed_password'][:50]}...")
    else:
        print("   [ERRO] Usuario nao encontrado")
        exit(1)
except Exception as e:
    print(f"   [ERRO] Erro ao buscar usuario: {e}")
    exit(1)

# 3. Testar validacao de senha
password = "2520@Selu"
print(f"\n3. Testando senha: {password}")

# Teste com bcrypt
try:
    password_bytes = password.encode('utf-8')
    hash_bytes = user['hashed_password'].encode('utf-8')
    result = bcrypt.checkpw(password_bytes, hash_bytes)

    if result:
        print("   [OK] Senha validada com sucesso (bcrypt)")
    else:
        print("   [ERRO] Senha invalida (bcrypt)")

        # Se falhou, vamos gerar um novo hash
        print("\n4. Gerando novo hash correto...")
        new_hash = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        new_hash_str = new_hash.decode('utf-8')
        print(f"   Novo hash: {new_hash_str}")

        # Atualizar no banco
        print("\n5. Atualizando hash no banco de dados...")
        try:
            update_response = supabase.table("usuarios")\
                .update({"hashed_password": new_hash_str})\
                .eq("email", email)\
                .execute()

            print("   [OK] Hash atualizado no banco!")
            print(f"   Execute novamente o teste ou tente fazer login")
        except Exception as e:
            print(f"   [ERRO] Erro ao atualizar: {e}")

except Exception as e:
    print(f"   [ERRO] Erro ao validar senha: {e}")

# 4. Verificar assinatura
print("\n6. Verificando assinatura do usuario...")
try:
    response = supabase.table("assinaturas")\
        .select("*, planos!inner(*)")\
        .eq("usuario_id", user['id'])\
        .eq("status", "ativa")\
        .execute()

    if response.data and len(response.data) > 0:
        assinatura = response.data[0]
        plano = assinatura.get("planos")
        print(f"   [OK] Assinatura encontrada")
        print(f"   - Plano: {plano.get('nome')}")
        print(f"   - Status: {assinatura.get('status')}")
        print(f"   - Data fim: {assinatura.get('data_fim')}")
        print(f"   - Modulos: {plano.get('modulos_disponiveis')}")
    else:
        print("   [ERRO] Nenhuma assinatura ativa encontrada")
except Exception as e:
    print(f"   [ERRO] Erro ao buscar assinatura: {e}")

print("\n" + "=" * 60)
