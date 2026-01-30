"""
Script para verificar se o hash da senha está correto
"""
import bcrypt
from passlib.context import CryptContext

# Hash que está no banco (do resultado da query SQL)
hash_from_db = "$2b$12$l5XuXtzigdE/jstnqmsChuapednBbnDd1MwHuMXqEH9f2ivWinSea"

# Senha que estamos tentando
password = "2520@Selu"

print("=" * 60)
print("VERIFICACAO DE SENHA")
print("=" * 60)
print(f"\nSenha testada: {password}")
print(f"\nHash no banco: {hash_from_db}")

# Teste 1: usando bcrypt diretamente
print("\n" + "-" * 60)
print("Teste 1: Usando bcrypt diretamente")
print("-" * 60)
try:
    password_bytes = password.encode('utf-8')
    hash_bytes = hash_from_db.encode('utf-8')
    result = bcrypt.checkpw(password_bytes, hash_bytes)
    print(f"Resultado: {'SENHA CORRETA' if result else 'SENHA INCORRETA'}")
except Exception as e:
    print(f"Erro: {str(e)}")

# Teste 2: usando passlib (como o backend usa)
print("\n" + "-" * 60)
print("Teste 2: Usando passlib (CryptContext)")
print("-" * 60)
try:
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    result = pwd_context.verify(password, hash_from_db)
    print(f"Resultado: {'SENHA CORRETA' if result else 'SENHA INCORRETA'}")
except Exception as e:
    print(f"Erro: {str(e)}")

# Teste 3: Gerar novo hash e comparar
print("\n" + "-" * 60)
print("Teste 3: Gerar novo hash da mesma senha")
print("-" * 60)
try:
    new_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    print(f"Novo hash gerado: {new_hash.decode('utf-8')}")
    print(f"Hash no banco:    {hash_from_db}")
    print(f"Sao iguais? {new_hash.decode('utf-8') == hash_from_db}")

    # Testar se o novo hash funciona
    result = bcrypt.checkpw(password.encode('utf-8'), new_hash)
    print(f"Novo hash valida a senha? {'SIM' if result else 'NAO'}")
except Exception as e:
    print(f"Erro: {str(e)}")

print("\n" + "=" * 60)
