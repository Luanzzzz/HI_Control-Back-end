"""
Testes unitários para core/security.py
"""
import pytest
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)


class TestPasswordHash:
    """Testa hashing e verificação de senhas"""

    def test_hash_diferente_do_original(self):
        senha = "minha_senha_123"
        hashed = get_password_hash(senha)
        assert hashed != senha

    def test_verificar_senha_correta(self):
        senha = "minha_senha_123"
        hashed = get_password_hash(senha)
        assert verify_password(senha, hashed) is True

    def test_verificar_senha_incorreta(self):
        senha = "minha_senha_123"
        hashed = get_password_hash(senha)
        assert verify_password("senha_errada", hashed) is False

    def test_hash_unico_para_mesma_senha(self):
        senha = "minha_senha_123"
        hash1 = get_password_hash(senha)
        hash2 = get_password_hash(senha)
        # bcrypt usa salt aleatório, então hashes são diferentes mas ambos válidos
        assert hash1 != hash2
        assert verify_password(senha, hash1) is True
        assert verify_password(senha, hash2) is True

    def test_hash_vazio(self):
        hashed = get_password_hash("")
        assert verify_password("", hashed) is True

    def test_verificar_contra_hash_invalido(self):
        resultado = verify_password("senha", "hash_invalido")
        assert resultado is False


class TestJWTTokens:
    """Testa criação e decodificação de tokens JWT"""

    def test_criar_access_token(self):
        dados = {"sub": "user-uuid-123", "email": "test@test.com"}
        token = create_access_token(dados)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_criar_refresh_token(self):
        dados = {"sub": "user-uuid-123"}
        token = create_refresh_token(dados)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_e_refresh_tokens_diferentes(self):
        dados = {"sub": "user-uuid-123"}
        access = create_access_token(dados)
        refresh = create_refresh_token(dados)
        assert access != refresh

    def test_decodificar_access_token(self):
        dados = {"sub": "user-uuid-123", "email": "test@test.com"}
        token = create_access_token(dados)
        payload = decode_token(token)
        assert payload["sub"] == "user-uuid-123"
        assert payload["email"] == "test@test.com"

    def test_decodificar_token_invalido(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_token("token_invalido")
        assert exc_info.value.status_code == 401

    def test_token_contém_sub(self):
        dados = {"sub": "user-uuid-456"}
        token = create_access_token(dados)
        payload = decode_token(token)
        assert payload is not None
        assert "sub" in payload

    def test_token_contém_exp(self):
        dados = {"sub": "user-uuid-123"}
        token = create_access_token(dados)
        payload = decode_token(token)
        assert payload is not None
        assert "exp" in payload
