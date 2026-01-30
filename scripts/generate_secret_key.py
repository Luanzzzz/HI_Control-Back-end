#!/usr/bin/env python3
"""
🔐 Gerador de SECRET_KEY para JWT - Hi-Control
Gera chaves criptograficamente seguras para uso em produção
"""

import secrets
import string

def generate_secret_key(length: int = 64) -> str:
    """Generate a cryptographically secure secret key"""
    # Use URL-safe characters (letters, numbers, -, _)
    return secrets.token_urlsafe(length)

def generate_strong_password(length: int = 32) -> str:
    """Generate a strong password with mixed characters"""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

def main():
    print("🔐 Hi-Control - Gerador de Chaves Seguras\n")
    print("="*60)
    
    # Generate SECRET_KEY for JWT
    secret_key = generate_secret_key(64)
    print("\n✅ SECRET_KEY (para JWT):")
    print(f"   {secret_key}")
    print("\n   → Configure no Vercel: Environment Variables → SECRET_KEY")
    
    # Generate alternative option
    secret_key_alt = generate_secret_key(48)
    print(f"\n   Alternativa (48 chars): {secret_key_alt}")
    
    # Usage instructions
    print("\n" + "="*60)
    print("\n📋 Como usar:")
    print("   1. Copie a SECRET_KEY acima")
    print("   2. Acesse Vercel Dashboard → Seu Projeto Backend")
    print("   3. Settings → Environment Variables")
    print("   4. Adicione: SECRET_KEY = [valor copiado]")
    print("   5. Selecione: Production, Preview, Development")
    print("   6. Save")
    print("\n⚠️  IMPORTANTE:")
    print("   - NUNCA commite esta chave no Git")
    print("   - Use a MESMA chave em todos os ambientes")
    print("   - Guarde em um gerenciador de senhas seguro")
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
