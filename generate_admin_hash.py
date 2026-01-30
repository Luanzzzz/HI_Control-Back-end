"""
Script para gerar hash da senha do administrador
Execute: python generate_admin_hash.py
"""
import bcrypt

# Senha solicitada
password = "2520@Selu"

# Gerar hash usando bcrypt diretamente
password_bytes = password.encode('utf-8')
salt = bcrypt.gensalt()
hashed = bcrypt.hashpw(password_bytes, salt)
hashed_str = hashed.decode('utf-8')

print("=" * 60)
print("HASH GERADO PARA A SENHA DO ADMINISTRADOR")
print("=" * 60)
print(f"\nSenha original: {password}")
print(f"\nHash bcrypt: {hashed_str}")
print("\nUse este hash no script SQL abaixo.")
print("=" * 60)
