#!/usr/bin/env python3
"""
Script de diagnóstico para testar conexão com Supabase
Verifica se credenciais estão corretas e se usuários existem no banco
"""

import sys
import os
from pathlib import Path

# Adicionar diretório raiz ao path
backend_path = Path(__file__).parent.parent
sys.path.append(str(backend_path))

from supabase import create_client, Client
from app.core.config import settings
import bcrypt


def test_connection():
    """Testa conexão básica com Supabase"""
    print("=" * 80)
    print("TESTE 1: Conexão com Supabase")
    print("=" * 80)
    
    try:
        print(f"URL: {settings.SUPABASE_URL}")
        print(f"Anon Key: {settings.SUPABASE_KEY[:20]}...")
        print(f"Service Key: {settings.SUPABASE_SERVICE_KEY[:20]}...")
        
        # Criar cliente admin
        client: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY
        )
        
        print("✅ Cliente Supabase criado com sucesso")
        return client
        
    except Exception as e:
        print(f"❌ Erro ao criar cliente: {e}")
        return None


def test_list_users(client: Client):
    """Lista todos os usuários do banco"""
    print("\n" + "=" * 80)
    print("TESTE 2: Listar Usuários")
    print("=" * 80)
    
    try:
        response = client.table("usuarios").select("id, email, nome_completo, ativo, email_verificado").execute()
        
        if not response.data:
            print("❌ NENHUM USUÁRIO ENCONTRADO NO BANCO!")
            return []
        
        print(f"✅ {len(response.data)} usuário(s) encontrado(s):\n")
        
        for user in response.data:
            status = "✅ ATIVO" if user.get("ativo") else "❌ INATIVO"
            verified = "✅ VERIFICADO" if user.get("email_verificado") else "⚠️  NÃO VERIFICADO"
            print(f"  • Email: {user['email']}")
            print(f"    Nome: {user['nome_completo']}")
            print(f"    Status: {status} | {verified}")
            print(f"    ID: {user['id']}")
            print()
        
        return response.data
        
    except Exception as e:
        print(f"❌ Erro ao listar usuários: {e}")
        return []


def test_find_user(client: Client, email: str):
    """Busca usuário específico por email"""
    print("\n" + "=" * 80)
    print(f"TESTE 3: Buscar Usuário '{email}'")
    print("=" * 80)
    
    try:
        response = client.table("usuarios")\
            .select("*")\
            .eq("email", email)\
            .single()\
            .execute()
        
        if not response.data:
            print(f"❌ Usuário '{email}' NÃO ENCONTRADO")
            return None
        
        user = response.data
        print("✅ Usuário encontrado:")
        print(f"  • Email: {user['email']}")
        print(f"  • Nome: {user['nome_completo']}")
        print(f"  • Ativo: {user.get('ativo')}")
        print(f"  • Email Verificado: {user.get('email_verificado')}")
        print(f"  • Tem Hash de Senha: {'SIM' if user.get('hashed_password') else 'NÃO'}")
        print(f"  • ID: {user['id']}")
        
        return user
        
    except Exception as e:
        print(f"❌ Erro ao buscar usuário: {e}")
        return None


def test_password_hash(password: str, hashed_password: str):
    """Testa se hash de senha está correto"""
    print("\n" + "=" * 80)
    print("TESTE 4: Verificar Hash de Senha")
    print("=" * 80)
    
    try:
        password_bytes = password.encode('utf-8')
        hash_bytes = hashed_password.encode('utf-8')
        
        is_valid = bcrypt.checkpw(password_bytes, hash_bytes)
        
        if is_valid:
            print("✅ Hash de senha VÁLIDO")
        else:
            print("❌ Hash de senha INVÁLIDO")
            
        return is_valid
        
    except Exception as e:
        print(f"❌ Erro ao verificar hash: {e}")
        return False


def main():
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "DIAGNÓSTICO DE AUTENTICAÇÃO HI-CONTROL" + " " * 20 + "║")
    print("╚" + "=" * 78 + "╝")
    print("\n")
    
    # Teste 1: Conexão
    client = test_connection()
    if not client:
        print("\n❌ FALHA CRÍTICA: Não foi possível conectar ao Supabase")
        print("Verifique as credenciais no arquivo .env")
        return
    
    # Teste 2: Listar usuários
    users = test_list_users(client)
    
    if not users:
        print("\n🔴 DIAGNÓSTICO: O banco está VAZIO!")
        print("   Ação necessária: Executar SQL para criar usuários")
        return
    
    # Teste 3: Buscar usuário específico
    test_emails = [
        "luan.valentino78@gmail.com",
        "socio.teste@hicontrol.com.br",
        "teste@hicontrol.com.br"
    ]
    
    for email in test_emails:
        user = test_find_user(client, email)
        
        # Teste 4: Se encontrou usuário, testar senha
        if user and user.get('hashed_password'):
            # Testar com senhas conhecidas
            test_passwords = {
                "luan.valentino78@gmail.com": "HiControl@Admin2026",
                "socio.teste@hicontrol.com.br": "HiControl@Partner2026",
                "teste@hicontrol.com.br": "HiControl@2024"
            }
            
            if email in test_passwords:
                test_password_hash(test_passwords[email], user['hashed_password'])
    
    print("\n" + "=" * 80)
    print("DIAGNÓSTICO COMPLETO")
    print("=" * 80)
    print("\nSe todos os testes passaram, o problema pode estar em:")
    print("  1. Frontend enviando credenciais incorretas")
    print("  2. Logs do backend (verifique o terminal do uvicorn)")
    print("  3. CORS bloqueando requisições")
    print("\n")


if __name__ == "__main__":
    main()
