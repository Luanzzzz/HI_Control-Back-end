#!/usr/bin/env python3
"""
🔍 Script de Verificação Pré-Deploy - Hi-Control
Verifica se todos os requisitos estão prontos para deploy no Vercel
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple

class Colors:
    """ANSI color codes"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Print section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_check(status: bool, message: str):
    """Print check result"""
    icon = f"{Colors.GREEN}✅" if status else f"{Colors.RED}❌"
    print(f"{icon} {message}{Colors.RESET}")

def check_file_exists(filepath: Path) -> bool:
    """Check if file exists"""
    return filepath.exists()

def check_env_variables(env_file: Path, required_vars: List[str]) -> Tuple[bool, List[str]]:
    """Check if required environment variables are defined"""
    if not env_file.exists():
        return False, required_vars
    
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    missing_vars = []
    for var in required_vars:
        if f"{var}=" not in content or f"{var}=your-" in content or f"{var}=sua-" in content:
            missing_vars.append(var)
    
    return len(missing_vars) == 0, missing_vars

def check_dependencies(requirements_file: Path) -> bool:
    """Check if requirements.txt is valid"""
    if not requirements_file.exists():
        return False
    
    with open(requirements_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Check if has at least fastapi and uvicorn
    has_fastapi = any('fastapi' in line.lower() for line in lines)
    has_uvicorn = any('uvicorn' in line.lower() for line in lines)
    
    return has_fastapi and has_uvicorn

def main():
    """Main verification script"""
    print_header("🔍 Hi-Control - Verificação Pré-Deploy Vercel")
    
    # Get project root - script está em backend/scripts/
    script_dir = Path(__file__).parent
    backend_dir = script_dir.parent  # backend/
    project_root = backend_dir.parent  # Hi_Control/
    frontend_dir = project_root / 'Hi_Control'
    
    all_checks_passed = True
    
    # ===== BACKEND CHECKS =====
    print_header("🔧 Backend (FastAPI)")
    
    # Check vercel.json
    backend_vercel_json = backend_dir / 'vercel.json'
    status = check_file_exists(backend_vercel_json)
    print_check(status, f"vercel.json existe em {backend_dir.name}/")
    all_checks_passed &= status
    
    # Check requirements.txt
    requirements = backend_dir / 'requirements.txt'
    status = check_dependencies(requirements)
    print_check(status, "requirements.txt contém FastAPI e Uvicorn")
    all_checks_passed &= status
    
    # Check main.py
    main_py = backend_dir / 'app' / 'main.py'
    status = check_file_exists(main_py)
    print_check(status, "app/main.py (entry point) existe")
    all_checks_passed &= status
    
    # Check .env (local)
    backend_env = backend_dir / '.env'
    required_backend_vars = [
        'SECRET_KEY',
        'SUPABASE_URL',
        'SUPABASE_KEY',
        'CORS_ORIGINS'
    ]
    status, missing = check_env_variables(backend_env, required_backend_vars)
    if status:
        print_check(True, ".env contém todas as variáveis necessárias (local)")
    else:
        print_check(False, f".env faltando: {', '.join(missing)}")
        print(f"{Colors.YELLOW}   ⚠️  Configure no painel Vercel: Settings → Environment Variables{Colors.RESET}")
    
    # ===== FRONTEND CHECKS =====
    print_header("🎨 Frontend (React/Vite)")
    
    # Check vercel.json
    frontend_vercel_json = frontend_dir / 'vercel.json'
    status = check_file_exists(frontend_vercel_json)
    print_check(status, f"vercel.json existe em {frontend_dir.name}/")
    all_checks_passed &= status
    
    # Check package.json
    package_json = frontend_dir / 'package.json'
    status = check_file_exists(package_json)
    print_check(status, "package.json existe")
    all_checks_passed &= status
    
    # Check vite.config.ts
    vite_config = frontend_dir / 'vite.config.ts'
    status = check_file_exists(vite_config)
    print_check(status, "vite.config.ts configurado")
    all_checks_passed &= status
    
    # Check .env
    frontend_env = frontend_dir / '.env'
    if check_file_exists(frontend_env):
        with open(frontend_env, 'r', encoding='utf-8') as f:
            env_content = f.read()
        
        uses_env_var = 'VITE_API_URL' in env_content
        print_check(uses_env_var, "Usa VITE_API_URL para API base URL")
        
        # Check if not hardcoded to localhost in production
        if 'localhost' in env_content:
            print(f"{Colors.YELLOW}   ⚠️  .env contém 'localhost' - Configure VITE_API_URL no Vercel para produção{Colors.RESET}")
    else:
        print_check(False, ".env não encontrado")
        print(f"{Colors.YELLOW}   ⚠️  Configure VITE_API_URL no painel Vercel{Colors.RESET}")
    
    # Check src/services/api.ts
    api_service = frontend_dir / 'src' / 'services' / 'api.ts'
    if check_file_exists(api_service):
        with open(api_service, 'r', encoding='utf-8') as f:
            api_content = f.read()
        
        uses_import_meta = 'import.meta.env.VITE_API_URL' in api_content
        print_check(uses_import_meta, "api.ts usa import.meta.env.VITE_API_URL")
        all_checks_passed &= uses_import_meta
    else:
        print_check(False, "src/services/api.ts não encontrado")
        all_checks_passed = False
    
    # ===== SUMMARY =====
    print_header("📊 Resumo")
    
    if all_checks_passed:
        print(f"{Colors.GREEN}{Colors.BOLD}✅ TODOS OS CHECKS PASSARAM!{Colors.RESET}")
        print(f"\n{Colors.BLUE}🚀 Próximos passos:{Colors.RESET}")
        print(f"   1. cd backend && vercel (deploy backend)")
        print(f"   2. Configure variáveis no Vercel Dashboard")
        print(f"   3. Anote a URL do backend: https://hi-control-api-xxx.vercel.app")
        print(f"   4. cd ../Hi_Control && vercel (deploy frontend)")
        print(f"   5. Configure VITE_API_URL no Vercel com URL do backend")
        print(f"   6. Force redeploy do frontend: vercel --force")
        print(f"\n{Colors.BLUE}📖 Guia completo: DEPLOY_GUIDE.md{Colors.RESET}")
    else:
        print(f"{Colors.RED}{Colors.BOLD}❌ ALGUNS CHECKS FALHARAM{Colors.RESET}")
        print(f"\n{Colors.YELLOW}⚠️  Corrija os problemas acima antes de fazer deploy{Colors.RESET}")
        print(f"{Colors.BLUE}📖 Consulte: DEPLOY_GUIDE.md{Colors.RESET}")
        sys.exit(1)

if __name__ == "__main__":
    main()
