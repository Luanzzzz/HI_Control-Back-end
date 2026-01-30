import sys
import os
from datetime import date

# Add backend to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Mock env vars for config
os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
os.environ["SUPABASE_KEY"] = "mock-key"
os.environ["SUPABASE_SERVICE_KEY"] = "mock-service-key"
os.environ["SECRET_KEY"] = "mock-secret-key"

def test_imports():
    print("Testing imports...")
    try:
        from app.api.v1.endpoints import empresas, perfil
        from app.models.empresa import EmpresaCreate, EmpresaBase
        from app.models.perfil import PerfilCreate
        print("✅ Imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_empresa_validation():
    print("\nTesting Empresa valdiation...")
    from app.models.empresa import EmpresaCreate
    
    # Valid Case
    try:
        EmpresaCreate(
            usuario_id="123",
            razao_social="Empresa Teste",
            cnpj="12345678000190", # 14 digits
            regime_tributario="simples_nacional"
        )
        print("✅ EmpresaCreate valid data: OK")
    except Exception as e:
        print(f"❌ EmpresaCreate valid data failed: {e}")

    # Invalid CNPJ Length
    try:
        EmpresaCreate(
            usuario_id="123",
            razao_social="Empresa Teste",
            cnpj="123", # Invalid
        )
        print("❌ EmpresaCreate invalid CNPJ should fail but passed")
    except ValueError as e:
        print(f"✅ EmpresaCreate invalid CNPJ caught: {e}")
    except Exception as e:
         print(f"❌ EmpresaCreate invalid CNPJ unexpected error: {e}")

def test_perfil_validation():
    print("\nTesting Perfil validation...")
    from app.models.perfil import PerfilCreate
    
    # Valid Case
    try:
        PerfilCreate(
            nome_empresa="Contabilidade Silva",
            cnpj="12345678000190"
        )
        print("✅ PerfilCreate valid data: OK")
    except Exception as e:
        print(f"❌ PerfilCreate valid data failed: {e}")

if __name__ == "__main__":
    if test_imports():
        test_empresa_validation()
        test_perfil_validation()
    else:
        sys.exit(1)
