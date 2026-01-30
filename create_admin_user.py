"""
Script para criar usuario administrador diretamente via Python/Supabase
Este script vai:
1. Limpar usuarios existentes
2. Criar o usuario admin com senha correta
3. Criar assinatura premium
"""
import bcrypt
from supabase import create_client, Client
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# Configuracao Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")  # Usar service key para bypass RLS

if not SUPABASE_KEY:
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    print("[AVISO] Usando SUPABASE_KEY ao inves de SERVICE_KEY")

print("=" * 60)
print("CRIAR USUARIO ADMINISTRADOR")
print("=" * 60)

# Dados do admin
ADMIN_EMAIL = "luan.valentino78@gmail.com"
ADMIN_PASSWORD = "2520@Selu"
ADMIN_NOME = "Luan Valentino"

# 1. Conectar ao Supabase
print("\n1. Conectando ao Supabase...")
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("   [OK] Conectado com sucesso")
except Exception as e:
    print(f"   [ERRO] Erro ao conectar: {e}")
    exit(1)

# 2. Gerar hash da senha
print("\n2. Gerando hash da senha...")
password_bytes = ADMIN_PASSWORD.encode('utf-8')
salt = bcrypt.gensalt()
hashed_password = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
print(f"   [OK] Hash gerado: {hashed_password[:50]}...")

# 3. Verificar se usuario ja existe
print(f"\n3. Verificando se usuario {ADMIN_EMAIL} existe...")
try:
    response = supabase.table("usuarios").select("id").eq("email", ADMIN_EMAIL).execute()
    if response.data and len(response.data) > 0:
        user_id = response.data[0]['id']
        print(f"   [INFO] Usuario existe (ID: {user_id}), atualizando senha...")

        # Atualizar senha
        supabase.table("usuarios").update({
            "hashed_password": hashed_password,
            "ativo": True,
            "email_verificado": True
        }).eq("email", ADMIN_EMAIL).execute()
        print("   [OK] Senha atualizada!")
    else:
        print("   [INFO] Usuario nao existe, criando...")

        # Criar usuario
        user_data = {
            "email": ADMIN_EMAIL,
            "nome_completo": ADMIN_NOME,
            "hashed_password": hashed_password,
            "ativo": True,
            "email_verificado": True
        }

        response = supabase.table("usuarios").insert(user_data).execute()
        if response.data:
            user_id = response.data[0]['id']
            print(f"   [OK] Usuario criado com ID: {user_id}")
        else:
            print("   [ERRO] Falha ao criar usuario")
            exit(1)

except Exception as e:
    print(f"   [ERRO] Erro: {e}")
    exit(1)

# 4. Buscar plano profissional
print("\n4. Buscando plano profissional...")
try:
    response = supabase.table("planos").select("id, nome").eq("nome", "profissional").execute()
    if response.data and len(response.data) > 0:
        plano_id = response.data[0]['id']
        print(f"   [OK] Plano encontrado: {response.data[0]['nome']} (ID: {plano_id})")
    else:
        print("   [ERRO] Plano profissional nao encontrado!")
        exit(1)
except Exception as e:
    print(f"   [ERRO] Erro ao buscar plano: {e}")
    exit(1)

# 5. Verificar/Criar assinatura
print("\n5. Verificando assinatura...")
try:
    # Buscar usuario ID atualizado
    response = supabase.table("usuarios").select("id").eq("email", ADMIN_EMAIL).single().execute()
    user_id = response.data['id']

    # Verificar assinatura existente
    response = supabase.table("assinaturas").select("id").eq("usuario_id", user_id).eq("status", "ativa").execute()

    if response.data and len(response.data) > 0:
        print(f"   [INFO] Assinatura ativa ja existe")
    else:
        print("   [INFO] Criando assinatura premium...")

        # Calcular datas
        data_inicio = datetime.now().strftime("%Y-%m-%d")
        data_fim = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

        assinatura_data = {
            "usuario_id": user_id,
            "plano_id": plano_id,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "tipo_cobranca": "anual",
            "status": "ativa",
            "valor_pago": 1970.00,
            "em_trial": False
        }

        response = supabase.table("assinaturas").insert(assinatura_data).execute()
        if response.data:
            print(f"   [OK] Assinatura criada!")
        else:
            print("   [ERRO] Falha ao criar assinatura")

except Exception as e:
    print(f"   [ERRO] Erro ao verificar/criar assinatura: {e}")

# 6. Verificacao final
print("\n6. Verificacao final...")
try:
    response = supabase.table("usuarios").select("*").eq("email", ADMIN_EMAIL).single().execute()
    user = response.data
    print(f"   Email: {user['email']}")
    print(f"   Nome: {user['nome_completo']}")
    print(f"   Ativo: {user['ativo']}")
    print(f"   Hash: {user['hashed_password'][:30]}...")

    # Testar senha
    result = bcrypt.checkpw(ADMIN_PASSWORD.encode('utf-8'), user['hashed_password'].encode('utf-8'))
    print(f"   Senha valida: {result}")

except Exception as e:
    print(f"   [ERRO] Erro na verificacao: {e}")

print("\n" + "=" * 60)
print("PRONTO! Tente fazer login com:")
print(f"   Email: {ADMIN_EMAIL}")
print(f"   Senha: {ADMIN_PASSWORD}")
print("=" * 60)
