"""
Testes unitários para o módulo NFS-e.

Testa:
- Seleção de adapter por município
- Validação de CNPJ
- Processamento de respostas das APIs
- Geração de chave NFS-e
- Normalização de status
"""
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.nfse.base_adapter import (
    BaseNFSeAdapter,
    NFSeException,
    NFSeAuthException,
    NFSeSearchException,
    NFSeConfigException,
)
from app.services.nfse.sistema_nacional import SistemaNacionalAdapter
from app.services.nfse.belo_horizonte import BeloHorizonteAdapter
from app.services.nfse.sao_paulo import SaoPauloAdapter
from app.services.nfse.nfse_service import NFSeService


# ============================================
# TESTES DE SELEÇÃO DE ADAPTER
# ============================================

class TestNFSeServiceAdapterSelection:
    """Testes para seleção correta de adapter por município."""

    def setup_method(self):
        self.service = NFSeService()
        self.credentials = {"usuario": "teste", "senha": "teste123"}

    def test_selecionar_adapter_belo_horizonte(self, monkeypatch):
        """Deve retornar BeloHorizonteAdapter para código IBGE 3106200."""
        monkeypatch.setenv("NFSE_FORCAR_SISTEMA_NACIONAL", "false")
        adapter = self.service.obter_adapter("3106200", self.credentials)
        assert isinstance(adapter, BeloHorizonteAdapter)

    def test_selecionar_adapter_sao_paulo(self, monkeypatch):
        """Deve retornar SaoPauloAdapter para código IBGE 3550308."""
        monkeypatch.setenv("NFSE_FORCAR_SISTEMA_NACIONAL", "false")
        adapter = self.service.obter_adapter("3550308", self.credentials)
        assert isinstance(adapter, SaoPauloAdapter)

    def test_selecionar_adapter_sistema_nacional_fallback(self, monkeypatch):
        """Deve retornar SistemaNacionalAdapter para município sem implementação específica."""
        monkeypatch.setenv("NFSE_FORCAR_SISTEMA_NACIONAL", "false")
        adapter = self.service.obter_adapter("1234567", self.credentials)
        assert isinstance(adapter, SistemaNacionalAdapter)

    def test_selecionar_adapter_codigo_vazio(self, monkeypatch):
        """Deve retornar SistemaNacionalAdapter quando código está vazio."""
        monkeypatch.setenv("NFSE_FORCAR_SISTEMA_NACIONAL", "false")
        adapter = self.service.obter_adapter("", self.credentials)
        assert isinstance(adapter, SistemaNacionalAdapter)

    def test_adapter_recebe_credenciais(self, monkeypatch):
        """Adapter deve receber as credenciais passadas."""
        monkeypatch.setenv("NFSE_FORCAR_SISTEMA_NACIONAL", "false")
        adapter = self.service.obter_adapter("3106200", self.credentials)
        assert adapter.credentials == self.credentials

    def test_adapter_ambiente_homologacao(self, monkeypatch):
        """Deve configurar ambiente de homologação quando solicitado."""
        monkeypatch.setenv("NFSE_FORCAR_SISTEMA_NACIONAL", "false")
        adapter = self.service.obter_adapter(
            "3106200", self.credentials, homologacao=True
        )
        assert isinstance(adapter, BeloHorizonteAdapter)
        assert adapter.homologacao is True


# ============================================
# TESTES DE VALIDAÇÃO DE CNPJ
# ============================================

class TestCNPJValidation:
    """Testes para validação de formato CNPJ."""

    def setup_method(self):
        self.adapter = SistemaNacionalAdapter(
            {"usuario": "test", "senha": "test"}
        )

    def test_cnpj_valido_sem_formatacao(self):
        """CNPJ com 14 dígitos sem formatação deve ser válido."""
        assert self.adapter.validar_cnpj("18039919000154") is True

    def test_cnpj_valido_com_formatacao(self):
        """CNPJ com formatação (pontos, barra, traço) deve ser válido."""
        assert self.adapter.validar_cnpj("18.039.919/0001-54") is True

    def test_cnpj_invalido_curto(self):
        """CNPJ com menos de 14 dígitos deve ser inválido."""
        assert self.adapter.validar_cnpj("123") is False

    def test_cnpj_invalido_letras(self):
        """CNPJ com letras deve ser inválido."""
        assert self.adapter.validar_cnpj("abcdefghijklmn") is False

    def test_cnpj_invalido_vazio(self):
        """CNPJ vazio deve ser inválido."""
        assert self.adapter.validar_cnpj("") is False

    def test_limpar_cnpj(self):
        """Deve remover formatação do CNPJ corretamente."""
        assert self.adapter.limpar_cnpj("18.039.919/0001-54") == "18039919000154"
        assert self.adapter.limpar_cnpj("18039919000154") == "18039919000154"
        assert self.adapter.limpar_cnpj("") == ""


# ============================================
# TESTES DE PROCESSAMENTO DE RESPOSTA
# ============================================

class TestSistemaNacionalProcessamento:
    """Testes para processamento de respostas do Sistema Nacional."""

    def setup_method(self):
        self.adapter = SistemaNacionalAdapter(
            {"usuario": "test", "senha": "test"}
        )

    def test_processar_resposta_vazia(self):
        """Resposta sem notas deve retornar lista vazia."""
        result = self.adapter.processar_resposta({})
        assert result == []

    def test_processar_resposta_com_notas(self):
        """Deve processar notas corretamente."""
        resposta = {
            "nfse": [
                {
                    "numero": "12345",
                    "dataEmissao": "2026-02-01",
                    "valorTotal": 1500.00,
                    "cnpjPrestador": "18039919000154",
                    "razaoSocialPrestador": "EMPRESA TESTE LTDA",
                    "cnpjTomador": "12345678000190",
                    "razaoSocialTomador": "CLIENTE TESTE",
                    "discriminacao": "Serviço de consultoria",
                    "codigoVerificacao": "ABC123",
                    "codigoMunicipio": "3106200",
                    "municipioNome": "Belo Horizonte",
                }
            ]
        }

        result = self.adapter.processar_resposta(resposta)

        assert len(result) == 1
        nota = result[0]
        assert nota["tipo"] == "NFS-e"
        assert nota["numero"] == "12345"
        assert nota["valor_total"] == 1500.00
        assert nota["cnpj_prestador"] == "18039919000154"
        assert nota["prestador_nome"] == "EMPRESA TESTE LTDA"
        assert nota["cnpj_tomador"] == "12345678000190"
        assert nota["tomador_nome"] == "CLIENTE TESTE"
        assert nota["descricao_servico"] == "Serviço de consultoria"
        assert nota["codigo_verificacao"] == "ABC123"

    def test_processar_resposta_com_objetos_aninhados(self):
        """Deve processar notas com dados em sub-objetos."""
        resposta = {
            "notas": [
                {
                    "numero": "999",
                    "dataEmissao": "2026-01-15",
                    "prestador": {
                        "cnpj": "18039919000154",
                        "razaoSocial": "PRESTADOR ANINHADO",
                    },
                    "tomador": {
                        "cnpj": "98765432000100",
                        "razaoSocial": "TOMADOR ANINHADO",
                    },
                    "valores": {
                        "valorServicos": 2500.00,
                        "valorIss": 125.00,
                        "aliquota": 5.0,
                        "discriminacao": "Serviço aninhado",
                    },
                }
            ]
        }

        result = self.adapter.processar_resposta(resposta)

        assert len(result) == 1
        nota = result[0]
        assert nota["numero"] == "999"
        assert nota["cnpj_prestador"] == "18039919000154"
        assert nota["prestador_nome"] == "PRESTADOR ANINHADO"
        assert nota["valor_total"] == 2500.00
        assert nota["valor_iss"] == 125.00

    def test_processar_nota_com_erro_nao_quebra(self):
        """Nota com dados inválidos deve ser ignorada sem quebrar processamento."""
        resposta = {
            "nfse": [
                None,  # Nota inválida
                {
                    "numero": "100",
                    "dataEmissao": "2026-01-01",
                    "valorTotal": 500.0,
                },
            ]
        }

        result = self.adapter.processar_resposta(resposta)
        # Deve ter processado a nota válida e ignorado None
        assert len(result) >= 1


class TestBeloHorizonteProcessamento:
    """Testes para processamento de respostas de BH."""

    def setup_method(self):
        self.adapter = BeloHorizonteAdapter(
            {"usuario": "test", "senha": "test"}
        )

    def test_municipio_fixo(self):
        """Notas de BH devem ter código IBGE fixo."""
        resposta = {
            "listaNotas": [
                {
                    "numero": "1",
                    "dataEmissao": "2026-02-01",
                    "valorTotal": 100.0,
                }
            ]
        }

        result = self.adapter.processar_resposta(resposta)
        assert len(result) == 1
        assert result[0]["municipio_codigo"] == "3106200"
        assert result[0]["municipio_nome"] == "Belo Horizonte"


class TestSaoPauloProcessamento:
    """Testes para processamento de respostas de SP."""

    def setup_method(self):
        self.adapter = SaoPauloAdapter(
            {"usuario": "test", "senha": "test"}
        )

    def test_municipio_fixo(self):
        """Notas de SP devem ter código IBGE fixo."""
        resposta = {
            "NFe": [
                {
                    "NumeroNFe": "1001",
                    "DataEmissao": "2026-02-01",
                    "ValorServicos": 3000.0,
                }
            ]
        }

        result = self.adapter.processar_resposta(resposta)
        assert len(result) == 1
        assert result[0]["municipio_codigo"] == "3550308"
        assert result[0]["municipio_nome"] == "São Paulo"

    def test_campos_sp_mapeados(self):
        """Campos com nomenclatura SP devem ser mapeados corretamente."""
        resposta = {
            "NFe": [
                {
                    "NumeroNFe": "2002",
                    "SerieNFe": "A",
                    "DataEmissao": "2026-01-20",
                    "ValorServicos": 5000.0,
                    "CPFCNPJPrestador": "18.039.919/0001-54",
                    "RazaoSocialPrestador": "EMPRESA SP",
                    "CPFCNPJTomador": "12345678000190",
                    "RazaoSocialTomador": "CLIENTE SP",
                    "Discriminacao": "Desenvolvimento de software",
                    "CodigoVerificacao": "XYZ789",
                }
            ]
        }

        result = self.adapter.processar_resposta(resposta)
        nota = result[0]
        assert nota["numero"] == "2002"
        assert nota["serie"] == "A"
        assert nota["valor_total"] == 5000.0
        assert nota["cnpj_prestador"] == "18039919000154"
        assert nota["prestador_nome"] == "EMPRESA SP"
        assert nota["descricao_servico"] == "Desenvolvimento de software"
        assert nota["codigo_verificacao"] == "XYZ789"


# ============================================
# TESTES DO SERVIÇO ORQUESTRADOR
# ============================================

class TestNFSeServiceHelpers:
    """Testes para métodos auxiliares do NFSeService."""

    def setup_method(self):
        self.service = NFSeService()

    def test_gerar_chave_nfse(self):
        """Deve gerar chave única para NFS-e."""
        nota = {
            "municipio_codigo": "3106200",
            "numero": "12345",
            "codigo_verificacao": "ABC123",
            "cnpj_prestador": "18039919000154",
        }

        chave = self.service._gerar_chave_nfse(nota)

        assert chave.startswith("NFSE")
        assert len(chave) == 44
        assert chave[4:].isalnum()

    def test_gerar_chave_nfse_sem_codigo_verificacao(self):
        """Deve gerar chave mesmo sem código de verificação."""
        nota = {
            "municipio_codigo": "3550308",
            "numero": "999",
            "cnpj_prestador": "12345678000190",
        }

        chave = self.service._gerar_chave_nfse(nota)

        assert chave.startswith("NFSE")
        assert len(chave) <= 44

    def test_normalizar_status_autorizada(self):
        """Status 'autorizada' e similares devem normalizar para 'autorizada'."""
        assert self.service._normalizar_status("Autorizada") == "autorizada"
        assert self.service._normalizar_status("Normal") == "autorizada"
        assert self.service._normalizar_status("Ativa") == "autorizada"
        assert self.service._normalizar_status("Emitida") == "autorizada"

    def test_normalizar_status_cancelada(self):
        """Status de cancelamento devem normalizar para 'cancelada'."""
        assert self.service._normalizar_status("Cancelada") == "cancelada"
        assert self.service._normalizar_status("Substituida") == "cancelada"
        assert self.service._normalizar_status("Anulada") == "cancelada"

    def test_normalizar_status_desconhecido(self):
        """Status desconhecido deve defaultar para 'autorizada'."""
        assert self.service._normalizar_status("outro_status") == "autorizada"

    def test_listar_municipios_suportados(self):
        """Deve retornar lista de municípios com informações."""
        municipios = self.service.listar_municipios_suportados()

        assert len(municipios) >= 3  # BH, SP, Default
        codigos = [m["codigo_ibge"] for m in municipios]
        assert "3106200" in codigos
        assert "3550308" in codigos
        assert "default" in codigos

    def test_anexar_credencial_modo_certificado_a1(self):
        cred = self.service._anexar_certificado_nas_credenciais(  # noqa: SLF001
            {
                "id": "cred-1",
                "usuario": "AUTO_CERT_A1",
                "senha": None,
                "token": "AUTO_CERT_A1|NSU:0",
                "cnpj": "18039919000154",
                "municipio_codigo": "3106200",
            },
            {
                "cnpj": "18.039.919/0001-54",
                "municipio_codigo": "3106200",
                "certificado_a1": "base64-pfx",
                "certificado_senha_encrypted": "senha-enc",
            },
        )
        assert cred["modo_autenticacao"] == "certificado_a1"
        assert cred["certificado_a1"] == "base64-pfx"
        assert cred["certificado_senha_encrypted"] == "senha-enc"


# ============================================
# TESTES DE EXCEÇÕES
# ============================================

class TestNFSeExceptions:
    """Testes para hierarquia de exceções NFS-e."""

    def test_nfse_exception_base(self):
        """NFSeException deve ter código e mensagem."""
        exc = NFSeException("CODE", "mensagem teste")
        assert exc.codigo == "CODE"
        assert exc.mensagem == "mensagem teste"
        assert "[CODE]" in str(exc)

    def test_nfse_auth_exception(self):
        """NFSeAuthException deve ter código fixo."""
        exc = NFSeAuthException("Credenciais inválidas")
        assert exc.codigo == "NFSE_AUTH_ERROR"
        assert exc.mensagem == "Credenciais inválidas"
        assert isinstance(exc, NFSeException)

    def test_nfse_search_exception(self):
        """NFSeSearchException deve ter código fixo."""
        exc = NFSeSearchException("Timeout", detalhes="30s")
        assert exc.codigo == "NFSE_SEARCH_ERROR"
        assert exc.detalhes == "30s"
        assert isinstance(exc, NFSeException)

    def test_nfse_config_exception(self):
        """NFSeConfigException deve ter código fixo."""
        exc = NFSeConfigException("URL inválida")
        assert exc.codigo == "NFSE_CONFIG_ERROR"
        assert isinstance(exc, NFSeException)


# ============================================
# TESTES DE CRIAR NOTA PADRÃO
# ============================================

class TestCriarNotaPadrao:
    """Testes para criação de nota no formato padrão."""

    def setup_method(self):
        self.adapter = SistemaNacionalAdapter(
            {"usuario": "test", "senha": "test"}
        )

    def test_criar_nota_com_campos_padrao(self):
        """Nota criada deve ter todos os campos padrão."""
        nota = self.adapter.criar_nota_padrao(numero="123", valor_total=1000.0)

        assert nota["tipo"] == "NFS-e"
        assert nota["numero"] == "123"
        assert nota["valor_total"] == 1000.0
        assert nota["status"] == "Autorizada"  # Padrão
        assert "cnpj_prestador" in nota
        assert "cnpj_tomador" in nota
        assert "descricao_servico" in nota

    def test_criar_nota_sobrescreve_padrao(self):
        """Valores fornecidos devem sobrescrever os padrões."""
        nota = self.adapter.criar_nota_padrao(
            status="Cancelada",
            municipio_nome="Teste City",
        )

        assert nota["status"] == "Cancelada"
        assert nota["municipio_nome"] == "Teste City"
