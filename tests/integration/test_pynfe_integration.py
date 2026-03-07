"""
Testes de integracao do adapter PyNFE.

Por padrao este modulo esta marcado como `integration` e nao roda no comando
padrao do pytest (ver pytest.ini). Ele pode ser executado com:

    pytest -m integration tests/integration/test_pynfe_integration.py -v
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.adapters.pynfe_adapter import PyNFeAdapter
from app.models.nfe_completa import (
    COFINSItem,
    DestinatarioNFe,
    ICMSItem,
    ItemNFeBase,
    NotaFiscalCompletaCreate,
    PISItem,
    TransporteNFe,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def adapter() -> PyNFeAdapter:
    return PyNFeAdapter()


@pytest.fixture
def nfe_data_base() -> NotaFiscalCompletaCreate:
    item = ItemNFeBase(
        numero_item=1,
        codigo_produto="PROD001",
        descricao="PRODUTO TESTE HOMOLOGACAO",
        ncm="12345678",
        cfop="5102",
        unidade_comercial="UN",
        quantidade_comercial=Decimal("1.0000"),
        valor_unitario_comercial=Decimal("100.00"),
        valor_total_bruto=Decimal("100.00"),
        icms=ICMSItem(
            origem="0",
            cst="00",
            modalidade_bc=0,
            base_calculo=Decimal("100.00"),
            aliquota=Decimal("18.00"),
            valor=Decimal("18.00"),
        ),
        pis=PISItem(
            cst="01",
            base_calculo=Decimal("100.00"),
            aliquota=Decimal("1.65"),
            valor=Decimal("1.65"),
        ),
        cofins=COFINSItem(
            cst="01",
            base_calculo=Decimal("100.00"),
            aliquota=Decimal("7.60"),
            valor=Decimal("7.60"),
        ),
    )

    destinatario = DestinatarioNFe(
        cpf="12345678909",
        nome="CONSUMIDOR FINAL HOMOLOGACAO",
        logradouro="Rua Teste",
        numero="123",
        bairro="Centro",
        municipio="Sao Paulo",
        uf="SP",
        cep="01310100",
    )

    return NotaFiscalCompletaCreate(
        empresa_id="00000000-0000-0000-0000-000000000001",
        numero_nf="1",
        serie="1",
        modelo="55",
        tipo_operacao="1",
        ambiente="2",
        data_emissao=datetime(2026, 2, 1, 10, 0, 0),
        destinatario=destinatario,
        itens=[item],
        transporte=TransporteNFe(modalidade_frete=9),
    )


def test_adapter_declara_disponibilidade_boolean(adapter: PyNFeAdapter):
    assert isinstance(adapter.is_available(), bool)


def test_to_pynfe_emitente_converte_campos_basicos(adapter: PyNFeAdapter):
    if not adapter.is_available():
        pytest.skip("PyNFE nao disponivel no ambiente de teste")

    emitente = adapter.to_pynfe_emitente(
        {
            "cnpj": "12.345.678/0001-90",
            "razao_social": "EMPRESA TESTE LTDA",
            "inscricao_estadual": "123456789",
            "uf": "SP",
        }
    )

    assert emitente.cnpj == "12345678000190"
    assert emitente.razao_social == "EMPRESA TESTE LTDA"


def test_to_pynfe_cliente_converte_destinatario(adapter: PyNFeAdapter):
    if not adapter.is_available():
        pytest.skip("PyNFE nao disponivel no ambiente de teste")

    destinatario = DestinatarioNFe(
        cpf="12345678909",
        nome="CLIENTE TESTE",
        logradouro="Rua X",
        numero="100",
        bairro="Centro",
        municipio="Sao Paulo",
        uf="SP",
        cep="01310100",
        email="cliente@teste.com",
    )

    cliente = adapter.to_pynfe_cliente(destinatario)
    assert cliente.tipo_documento == "CPF"
    assert cliente.numero_documento == "12345678909"
    assert cliente.razao_social == "CLIENTE TESTE"


def test_to_pynfe_produto_converte_item(adapter: PyNFeAdapter):
    if not adapter.is_available():
        pytest.skip("PyNFE nao disponivel no ambiente de teste")

    item = ItemNFeBase(
        numero_item=1,
        codigo_produto="P001",
        descricao="PRODUTO 1",
        ncm="12345678",
        cfop="5102",
        unidade_comercial="UN",
        quantidade_comercial=Decimal("2.0000"),
        valor_unitario_comercial=Decimal("50.00"),
        valor_total_bruto=Decimal("100.00"),
        icms=ICMSItem(
            origem="0",
            cst="00",
            modalidade_bc=0,
            base_calculo=Decimal("100.00"),
            aliquota=Decimal("18.00"),
            valor=Decimal("18.00"),
        ),
        pis=PISItem(
            cst="01",
            base_calculo=Decimal("100.00"),
            aliquota=Decimal("1.65"),
            valor=Decimal("1.65"),
        ),
        cofins=COFINSItem(
            cst="01",
            base_calculo=Decimal("100.00"),
            aliquota=Decimal("7.60"),
            valor=Decimal("7.60"),
        ),
    )

    produto = adapter.to_pynfe_produto(item)
    assert produto.codigo == "P001"
    assert float(produto.valor_total_bruto) == 100.0


def test_gerar_xml_nfe_estrutura_basica(adapter: PyNFeAdapter, nfe_data_base: NotaFiscalCompletaCreate):
    if not adapter.is_available():
        pytest.skip("PyNFE nao disponivel no ambiente de teste")

    emitente = adapter.to_pynfe_emitente(
        {
            "cnpj": "12345678000190",
            "razao_social": "EMPRESA TESTE",
            "inscricao_estadual": "123456789",
            "cidade": "Sao Paulo",
            "uf": "SP",
            "cep": "01310100",
        }
    )
    cliente = adapter.to_pynfe_cliente(nfe_data_base.destinatario)
    nota = adapter.to_pynfe_nota_fiscal(
        nfe_data=nfe_data_base,
        emitente=emitente,
        cliente=cliente,
        empresa_dados={"cidade": "Sao Paulo", "uf": "SP"},
    )

    xml = adapter.gerar_xml_nfe(nota_fiscal=nota, ambiente="2")
    assert isinstance(xml, str)
    assert "NFe" in xml
