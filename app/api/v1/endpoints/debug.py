"""
Endpoints de diagnóstico - APENAS PARA DESENVOLVIMENTO
⚠️ REMOVER EM PRODUÇÃO
"""
from fastapi import APIRouter, Depends
from app.dependencies import get_current_user
import sys
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/pynfe-status")
async def pynfe_status(usuario: dict = Depends(get_current_user)):
    """
    Diagnóstico completo do PyNFE
    ⚠️ Endpoint de debug - remover em produção
    """
    from app.adapters.pynfe_adapter import PyNFeAdapter

    diagnostics = {
        "environment": os.getenv("ENVIRONMENT", "unknown"),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "cwd": os.getcwd(),
        "pythonpath": os.getenv("PYTHONPATH"),
        "pynfe_available": False,
        "initialization_attempted": PyNFeAdapter._initialization_attempted,
        "modules_loaded": list(PyNFeAdapter._modules.keys()),
        "import_error": None,
    }

    # Testar lazy import
    try:
        available = PyNFeAdapter.is_available()
        diagnostics["pynfe_available"] = available

        if available:
            diagnostics["modules_loaded"] = list(PyNFeAdapter._modules.keys())
            diagnostics["module_count"] = len(PyNFeAdapter._modules)

    except Exception as e:
        diagnostics["import_error"] = str(e)

    # Testar imports individuais
    diagnostics["individual_imports"] = {}

    modules_to_test = [
        'pynfe',
        'pynfe.entidades.emitente',
        'pynfe.processamento.serializacao',
        'pynfe.utils.assinatura',
        'cryptography',
        'lxml',
        'signxml',
        'pyOpenSSL',
    ]

    for module_name in modules_to_test:
        try:
            __import__(module_name)
            diagnostics["individual_imports"][module_name] = "✅ OK"
        except ImportError as e:
            diagnostics["individual_imports"][module_name] = f"❌ {str(e)}"
        except Exception as e:
            diagnostics["individual_imports"][module_name] = f"⚠️ {str(e)}"

    return diagnostics


@router.get("/python-packages")
async def python_packages(usuario: dict = Depends(get_current_user)):
    """Lista pacotes Python instalados (filtrados)"""
    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'list', '--format=json'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            import json
            packages = json.loads(result.stdout)

            # Filtrar apenas pacotes relevantes
            relevant = [
                p for p in packages
                if any(keyword in p['name'].lower() for keyword in ['pynfe', 'crypto', 'lxml', 'sign', 'ssl'])
            ]

            return {
                "status": "success",
                "relevant_packages": relevant,
                "total_packages": len(packages),
            }
        else:
            return {
                "status": "error",
                "stderr": result.stderr
            }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "error": "Comando pip list excedeu timeout de 10 segundos"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/environment")
async def environment_info(usuario: dict = Depends(get_current_user)):
    """Informações do ambiente de execução"""
    import platform

    return {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_implementation": platform.python_implementation(),
        "system": platform.system(),
        "release": platform.release(),
        "cwd": os.getcwd(),
        "environment_vars": {
            "ENVIRONMENT": os.getenv("ENVIRONMENT"),
            "PYTHONPATH": os.getenv("PYTHONPATH"),
            "DISABLE_MODULE_CHECK": os.getenv("DISABLE_MODULE_CHECK"),
            "CERTIFICATE_ENCRYPTION_KEY": "***" if os.getenv("CERTIFICATE_ENCRYPTION_KEY") else None,
        }
    }
