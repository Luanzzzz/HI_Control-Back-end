"""
Configurações globais de testes - Hi-Control Backend
"""
import pytest
import os
from unittest.mock import MagicMock, AsyncMock

# Configurar variáveis de ambiente para testes ANTES de qualquer import da app
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-32chars")
os.environ.setdefault("ENVIRONMENT", "test")


@pytest.fixture
def mock_supabase_client():
    """Mock do cliente Supabase para testes unitários"""
    mock = MagicMock()
    mock.table.return_value = mock
    mock.select.return_value = mock
    mock.eq.return_value = mock
    mock.neq.return_value = mock
    mock.gte.return_value = mock
    mock.lte.return_value = mock
    mock.or_.return_value = mock
    mock.order.return_value = mock
    mock.limit.return_value = mock
    mock.range.return_value = mock
    mock.single.return_value = mock
    mock.insert.return_value = mock
    mock.update.return_value = mock
    mock.delete.return_value = mock
    mock.execute.return_value = MagicMock(data=[], count=0)
    return mock


@pytest.fixture
def mock_usuario():
    """Mock de usuário autenticado para testes"""
    return {
        "id": "test-user-uuid-1234",
        "email": "teste@hicontrol.com.br",
        "ativo": True,
        "nome": "Usuário Teste",
    }


@pytest.fixture
def mock_empresa():
    """Mock de empresa para testes"""
    return {
        "id": "test-empresa-uuid-5678",
        "usuario_id": "test-user-uuid-1234",
        "razao_social": "Empresa Teste LTDA",
        "cnpj": "12.345.678/0001-95",
        "ativa": True,
    }
