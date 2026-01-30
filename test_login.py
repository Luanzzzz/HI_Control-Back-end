"""
Script de teste de autenticação
"""
import requests
from urllib.parse import urlencode

# Dados de login
username = "luan.valentino78@gmail.com"
password = "2520@Selu"

# Preparar dados no formato OAuth2PasswordRequestForm
data = {
    "username": username,
    "password": password
}

# Fazer requisição
url = "http://localhost:8000/api/v1/auth/login"
headers = {
    "Content-Type": "application/x-www-form-urlencoded"
}

print("=" * 60)
print("TESTE DE AUTENTICAÇÃO")
print("=" * 60)
print(f"\nURL: {url}")
print(f"Username: {username}")
print(f"Password: {password}")
print("\nEnviando requisição...")
print("-" * 60)

try:
    response = requests.post(url, data=data, headers=headers)

    print(f"\nStatus Code: {response.status_code}")
    print(f"\nResponse Headers:")
    for key, value in response.headers.items():
        print(f"  {key}: {value}")

    print(f"\nResponse Body:")
    print(response.text)

    if response.status_code == 200:
        print("\n✅ LOGIN REALIZADO COM SUCESSO!")
        json_data = response.json()
        print(f"\nAccess Token: {json_data.get('access_token')[:50]}...")
        print(f"Refresh Token: {json_data.get('refresh_token')[:50]}...")
    else:
        print("\n❌ FALHA NO LOGIN!")

except Exception as e:
    print(f"\n❌ ERRO AO FAZER REQUISIÇÃO: {str(e)}")

print("\n" + "=" * 60)
