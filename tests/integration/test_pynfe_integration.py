"""
Testes de integração PyNFE com SEFAZ.

ATENÇÃO: Estes testes fazem requisições REAIS para a SEFAZ de homologação.
Requerem certificado digital válido configurado.

Para executar:
    pytest backend/tests/integration/test_pynfe_integration.py -v -s

Pré-requisitos:
    - PyNFE 0.6.0 instalado
    - lxml, signxml instalados
    - Certificado digital A1 válido
    - Empresa cadastrada no sistema
"""
import pytest
from decimal import Decimal
from datetime import datetime

# Marcar todos os testes como integration
pytestmark = pytest.mark.integration

from app.models.nfe_completa import (
    NotaFiscalCompletaCreate,
    ItemNFeBase,
    DestinatarioNFe,
    TransporteNFe,
    ICMSItem,
    PISItem,
    COFINSItem,
)
from app.services.sefaz_service import sefaz_service
from app.adapters.pynfe_adapter import PyNFeAdapter

# Instância do adapter para testes
pynfe_adapter = PyNFeAdapter()

# Skip todos os testes do adapter se PyNFE não estiver disponível
pynfe_disponivel = PyNFeAdapter.is_available()
pynfe_skip = pytest.mark.skipif(
    not pynfe_disponivel,
    reason="PyNFE não disponível (dependência OpenSSL incompatível ou não instalado)"
)


@pytest.fixture
def destinatario_homologacao():
    """
    Destinatário válido para ambiente de homologação SEFAZ.
    """
    return DestinatarioNFe(
        cpf="12345678909",
        nome="NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
        logradouro="Rua Teste Homologacao",
        numero="123",
        bairro="Centro",
        municipio="Sao Paulo",
        uf="SP",
        cep="01310100",
    )


@pytest.fixture
def item_homologacao():
    """
    Item de NF-e válido para homologação.
    """
    return ItemNFeBase(
        numero_item=1,
        codigo_produto="PROD001",
        descricao="NOTA FISCAL EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL",
        ncm="12345678",
        cfop="5102",  # Venda de mercadoria
        unidade_comercial="UN",
        quantidade_comercial=Decimal("1.0000"),
        valor_unitario_comercial=Decimal("100.00"),
        valor_total_bruto=Decimal("100.00"),
        icms=ICMSItem(
            origem="0",  # Nacional
            cst="00",  # Tributada integralmente
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


@pytest.fixture
def nfe_completa_homologacao(destinatario_homologacao, item_homologacao):
    """
    NF-e completa para teste em homologação.
    """
    return NotaFiscalCompletaCreate(
        empresa_id="SUBSTITUIR_POR_ID_REAL",  # ⚠️ Ajustar conforme teste
        numero_nf="1",
        serie="1",
        modelo="55",  # NF-e
        tipo_operacao="1",  # Saída
        ambiente="2",  # Homologação
        data_emissao=datetime.now(),
        destinatario=destinatario_homologacao,
        itens=[item_homologacao],
        transporte=TransporteNFe(modalidade_frete=9),  # Sem frete
        informacoes_complementares="Nota fiscal de teste emitida em ambiente de homologacao SEFAZ",
    )


class TestPyNFeAdapter:
    """Testes do adapter PyNFE"""

    @pynfe_skip
    def test_to_pynfe_emitente(self):
        """Testa conversão de empresa para Emitente"""
        empresa_dados = {
            'cnpj': '12.345.678/0001-90',
            'razao_social': 'Empresa Teste Ltda',
            'inscricao_estadual': '123456789',
            'uf': 'SP',
        }

        emitente = pynfe_adapter.to_pynfe_emitente(empresa_dados)

        assert emitente is not None
        assert emitente.cnpj == '12345678000190'
        assert emitente.razao_social == 'Empresa Teste Ltda'

    @pynfe_skip
    def test_to_pynfe_cliente(self, destinatario_homologacao):
        """Testa conversão de destinatário para Cliente"""
        cliente = pynfe_adapter.to_pynfe_cliente(destinatario_homologacao)

        assert cliente is not None
        assert cliente.numero_documento == '12345678909'
        assert cliente.tipo_documento == 'CPF'

    @pynfe_skip
    def test_to_pynfe_produto(self, item_homologacao):
        """Testa conversão de item para Produto"""
        produto = pynfe_adapter.to_pynfe_produto(item_homologacao)

        assert produto is not None
        assert produto.codigo == 'PROD001'
        assert float(produto.valor_total_bruto) == 100.00


class TestSefazServiceIntegration:
    """
    Testes de integração com SEFAZ (requerem certificado e conexão).

    ⚠️ ATENÇÃO: Estes testes são DESABILITADOS por padrão.
    Para habilitar, remova o decorator @pytest.mark.skip
    """

    @pytest.mark.skip(reason="Requer certificado digital e configuração manual")
    def test_autorizar_nfe_homologacao_completo(
        self,
        nfe_completa_homologacao
    ):
        """
        Teste completo de autorização de NF-e em homologação.

        REQUISITOS PARA EXECUTAR:
        1. Certificado digital A1 válido
        2. Empresa cadastrada no banco de dados
        3. CERTIFICATE_ENCRYPTION_KEY configurada
        4. Atualizar empresa_id no fixture

        PASSOS:
        1. Carregar certificado do banco
        2. Construir XML com PyNFE
        3. Assinar digitalmente
        4. Enviar para SEFAZ homologação
        5. Parsear resposta

        RESULTADO ESPERADO:
        - Status 100 (autorizada) OU
        - Rejeição com código e motivo específicos
        """
        # TODO: Implementar após configurar certificado de teste
        pytest.fail("Teste requer configuração manual de certificado")

    @pytest.mark.skip(reason="Requer NF-e autorizada previamente")
    def test_consultar_nfe_homologacao(self):
        """
        Testa consulta de NF-e autorizada.

        Requer uma NF-e previamente autorizada em homologação.
        """
        chave_acesso = "35240112345678000190550010000001231234567890"

        # TODO: Implementar consulta
        pytest.fail("Teste requer NF-e autorizada previamente")


class TestXmlGeneration:
    """Testes de geração de XML"""

    @pynfe_skip
    def test_gerar_xml_nfe_estrutura(self, nfe_completa_homologacao):
        """
        Testa se XML gerado tem estrutura válida.

        Não envia para SEFAZ, apenas valida estrutura local.
        """
        from lxml import etree

        # Preparar dados
        empresa_dados = {
            'cnpj': '12345678000190',
            'razao_social': 'Empresa Teste',
            'inscricao_estadual': '123456789',
            'uf': 'SP',
        }

        # Converter para PyNFE
        emitente = pynfe_adapter.to_pynfe_emitente(empresa_dados)
        cliente = pynfe_adapter.to_pynfe_cliente(nfe_completa_homologacao.destinatario)
        nota_fiscal = pynfe_adapter.to_pynfe_nota_fiscal(
            nfe_data=nfe_completa_homologacao,
            emitente=emitente,
            cliente=cliente,
            empresa_dados=empresa_dados
        )

        # Gerar XML
        xml_nfe = pynfe_adapter.gerar_xml_nfe(
            nota_fiscal=nota_fiscal,
            ambiente="2"
        )

        # Validar estrutura
        assert xml_nfe.startswith('<?xml')
        assert 'NFe' in xml_nfe
        assert 'infNFe' in xml_nfe

        # Parsear para verificar XML bem formado
        root = etree.fromstring(xml_nfe.encode('utf-8'))
        assert root is not None


# ============================================
# INSTRUÇÕES DE USO
# ============================================

"""
COMO EXECUTAR ESTES TESTES:

1. TESTES UNITÁRIOS (não requerem SEFAZ):
   pytest backend/tests/integration/test_pynfe_integration.py::TestPyNFeAdapter -v

2. TESTES DE XML (não requerem SEFAZ):
   pytest backend/tests/integration/test_pynfe_integration.py::TestXmlGeneration -v

3. TESTES DE INTEGRAÇÃO SEFAZ (requerem configuração):
   a. Configure certificado digital
   b. Atualize empresa_id nos fixtures
   c. Remova @pytest.mark.skip dos testes
   d. Execute:
      pytest backend/tests/integration/test_pynfe_integration.py::TestSefazServiceIntegration -v -s

TROUBLESHOOTING:

- "PyNFE não instalado":
  pip install PyNFe==0.6.0

- "lxml não disponível":
  pip install lxml==5.1.0

- "Certificado inválido":
  Verifique se certificado está válido e senha correta

- "Timeout SEFAZ":
  Ambiente de homologação pode estar instável, tente novamente

- "Rejeição 539 (certificado vencido)":
  Renovar certificado digital
"""
