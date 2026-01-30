import argparse
import requests
import json
import sys

# Constants
DEFAULT_URL = "https://backend-gamma-cyan-75.vercel.app/api/v1"
# Login credentials (same as E2E test)
USERNAME = "luan.valentino78@gmail.com"
PASSWORD = "2520@Selu"

def login(base_url, username, password):
    print(f"[STEP] Authenticating as {username}...")
    try:
        response = requests.post(
            f"{base_url}/auth/login",
            data={"username": username, "password": password},
            timeout=10
        )
        response.raise_for_status()
        print("[SUCCESS] Login successful")
        return response.json()['access_token']
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Authentication failed: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text}")
        sys.exit(1)

def create_client(base_url, token):
    print(f"[STEP] Creating Test Client (Empresa)...")
    
    # Valid simulated payload
    payload = {
        "razao_social": "Test Client Verification Ltd",
        "nome_fantasia": "Test Client",
        "cnpj": "18039919000154", # From user screenshot
        "inscricao_estadual": "0021414300077",
        "inscricao_municipal": "700203937",
        "cep": "33920260",
        "cidade": "RIBEIRAO DAS NEVES",
        "estado": "MG",
        "regime_tributario": "simples_nacional",
        "email": "test@client.com",
        "ativa": True
    }
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # Try POST /empresas (No Trailing Slash - The fix)
    target_url = f"{base_url}/empresas"
    print(f"[INFO] Target POST URL: {target_url}")
    
    try:
        response = requests.post(target_url, json=payload, headers=headers, timeout=15)
        
        if response.status_code == 200 or response.status_code == 201:
            print(f"[SUCCESS] Client created! ID: {response.json().get('id')}")
            return True
        elif response.status_code == 307:
            print(f"[FAIL] Server returned 307 Redirect! Trailing slash issue NOT fixed.")
            return False
        else:
            print(f"[ERROR] Failed to create client. Status: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
         print(f"[ERROR] Request failed: {e}")
         return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Client Creation")
    parser.add_argument("--url", default=DEFAULT_URL, help="API Base URL")
    args = parser.parse_args()
    
    token = login(args.url, USERNAME, PASSWORD)
    create_client(args.url, token)
