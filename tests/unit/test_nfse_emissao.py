"""
Testes unitários para o módulo de emissão NFS-e.

Cobre:
- Cálculo IBS/CBS (LC 214/2025)
- Montagem do DPS Nacional (SEFIN)
- Sequenciamento de RPS
- Geração de DANFSE (PDF)
- Construção XML ABRASF
- Cancelamento NFS-e Nacional (endpoint)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal


# ============================================
# TESTES: calcular_ibs_cbs
# ============================================

class TestCalcularIbsCbs:
    """Testes para cálculo de IBS e CBS (LC 214/2025)."""

    def setup_method(self):
        from app.services.nfse.emissao_nfse_service import EmissaoNFSeService
        self.service = EmissaoNFSeService()

    def test_calculo_basico(self):
        resultado = self.service.calcular_ibs_cbs(
            valor_servicos=1000.0,
            aliquota_ibs=2.5,
            aliquota_cbs=8.8,
        )
        assert resultado["valor_ibs"] == 25.0
        assert resultado["valor_cbs"] == 88.0
        assert resultado["aliquota_ibs"] == 2.5
        assert resultado["aliquota_cbs"] == 8.8

    def test_simples_nacional_zera_tributos(self):
        resultado = self.service.calcular_ibs_cbs(
            valor_servicos=5000.0,
            optante_simples=True,
            aliquota_ibs=2.5,
            aliquota_cbs=8.8,
        )
        assert resultado["valor_ibs"] == 0.0
        assert resultado["valor_cbs"] == 0.0

    def test_aliquotas_zeradas(self):
        """Durante período de transição as alíquotas podem ser 0."""
        resultado = self.service.calcular_ibs_cbs(
            valor_servicos=3000.0,
            aliquota_ibs=0.0,
            aliquota_cbs=0.0,
        )
        assert resultado["valor_ibs"] == 0.0
        assert resultado["valor_cbs"] == 0.0

    def test_arredondamento_dois_decimais(self):
        """Valores devem ser arredondados a 2 casas decimais."""
        resultado = self.service.calcular_ibs_cbs(
            valor_servicos=333.33,
            aliquota_ibs=3.0,
            aliquota_cbs=8.8,
        )
        assert resultado["valor_ibs"] == round(333.33 * 3 / 100, 2)
        assert resultado["valor_cbs"] == round(333.33 * 8.8 / 100, 2)

    def test_valor_alto(self):
        resultado = self.service.calcular_ibs_cbs(
            valor_servicos=100_000.0,
            aliquota_ibs=1.5,
            aliquota_cbs=9.6,
        )
        assert resultado["valor_ibs"] == 1500.0
        assert resultado["valor_cbs"] == 9600.0


# ============================================
# TESTES: montagem do DPS Nacional
# ============================================

class TestMontarDPS:
    """Testes para montagem do DPS (Documento Padrão de Serviço)."""

    def setup_method(self):
        from app.services.nfse.emissao_nfse_nacional_service import NFSeNacionalService
        self.service = NFSeNacionalService()

        self.empresa = {
            "cnpj": "12345678000199",
            "razao_social": "Empresa Teste Ltda",
            "inscricao_municipal": "123456",
        }

        self.dados_emissao = {
            "tomador": {
                "cnpj": "98765432000100",
                "nome": "Cliente Teste Ltda",
            },
            "servico": {
                "codigo_tributacao_nacional": "01.01",
                "discriminacao": "Desenvolvimento de software sob encomenda",
                "valor_servicos": 5000.0,
                "codigo_municipio": "3550308",
            },
            "tributos": {
                "ibs": {"aliquota": 0.0, "valor": 0.0},
                "cbs": {"aliquota": 0.0, "valor": 0.0},
            },
        }

    def test_dps_retorna_xml_valido(self):
        from lxml import etree
        xml_str = self.service.montar_dps(
            dados_emissao=self.dados_emissao,
            empresa=self.empresa,
            ambiente="homologacao",
        )
        assert isinstance(xml_str, str)
        # Deve parsear sem erro
        root = etree.fromstring(xml_str.encode("utf-8"))
        assert root is not None

    def test_dps_contem_cnpj_prestador(self):
        xml_str = self.service.montar_dps(
            dados_emissao=self.dados_emissao,
            empresa=self.empresa,
        )
        assert "12345678000199" in xml_str

    def test_dps_contem_cnpj_tomador(self):
        xml_str = self.service.montar_dps(
            dados_emissao=self.dados_emissao,
            empresa=self.empresa,
        )
        assert "98765432000100" in xml_str

    def test_dps_ambiente_homologacao(self):
        xml_str = self.service.montar_dps(
            dados_emissao=self.dados_emissao,
            empresa=self.empresa,
            ambiente="homologacao",
        )
        assert "<tpAmb>2</tpAmb>" in xml_str

    def test_dps_ambiente_producao(self):
        xml_str = self.service.montar_dps(
            dados_emissao=self.dados_emissao,
            empresa=self.empresa,
            ambiente="producao",
        )
        assert "<tpAmb>1</tpAmb>" in xml_str

    def test_dps_contem_discriminacao(self):
        xml_str = self.service.montar_dps(
            dados_emissao=self.dados_emissao,
            empresa=self.empresa,
        )
        assert "Desenvolvimento de software sob encomenda" in xml_str

    def test_dps_tomador_cpf(self):
        """Deve usar tag CPF quando tomador tem CPF (PF)."""
        dados = dict(self.dados_emissao)
        dados["tomador"] = {"cpf": "12345678901", "nome": "João Silva"}
        xml_str = self.service.montar_dps(
            dados_emissao=dados,
            empresa=self.empresa,
        )
        assert "<CPF>12345678901</CPF>" in xml_str

    def test_dps_falha_sem_cnpj_prestador(self):
        empresa_incompleta = {"razao_social": "Sem CNPJ"}
        with pytest.raises(ValueError, match="CNPJ"):
            self.service.montar_dps(
                dados_emissao=self.dados_emissao,
                empresa=empresa_incompleta,
            )

    def test_dps_falha_sem_discriminacao(self):
        dados = dict(self.dados_emissao)
        dados["servico"] = {
            "codigo_tributacao_nacional": "01.01",
            "valor_servicos": 100.0,
            # discriminacao ausente
        }
        with pytest.raises(ValueError, match="iscrimina"):
            self.service.montar_dps(
                dados_emissao=dados,
                empresa=self.empresa,
            )

    def test_dps_escapa_caracteres_xml(self):
        dados = dict(self.dados_emissao)
        dados["servico"] = dict(self.dados_emissao["servico"])
        dados["servico"]["discriminacao"] = "Serviço & teste <especial>"
        xml_str = self.service.montar_dps(
            dados_emissao=dados,
            empresa=self.empresa,
        )
        assert "&amp;" in xml_str or "Servi" in xml_str
        # Não deve ter < ou & crus no valor do campo
        from lxml import etree
        # Se parsear sem erro, o XML está bem formado
        etree.fromstring(xml_str.encode("utf-8"))


# ============================================
# TESTES: DANFSE (geração de PDF)
# ============================================

class TestDanfseService:
    """Testes para geração de DANFSE em PDF."""

    def setup_method(self):
        from app.services.danfse_service import DanfseService
        self.service = DanfseService()

        self.dados_base = {
            "numero_nf": "000001",
            "chave_acesso": "12345678901234567890123456789012345678901234",
            "codigo_verificacao": "ABCD-1234",
            "situacao": "autorizada",
            "data_emissao": "2026-04-10T10:00:00",
            "cnpj_destinatario": "12345678000199",
            "nome_destinatario": "Cliente Teste Ltda",
            "descricao_servico": "Desenvolvimento de software",
            "codigo_servico": "01.01",
            "valor_total": 5000.0,
            "valor_iss": 100.0,
            "aliquota_iss": 2.0,
            "tipo_nf": "NFSE",
        }

        self.empresa = {
            "razao_social": "Prestadora Teste Ltda",
            "cnpj": "98765432000100",
            "inscricao_municipal": "99999",
            "municipio_nome": "São Paulo",
            "uf": "SP",
        }

    def test_gerar_retorna_bytes(self):
        pdf = self.service.gerar_danfse(dados=self.dados_base, empresa=self.empresa)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0

    def test_pdf_tem_header_valido(self):
        pdf = self.service.gerar_danfse(dados=self.dados_base, empresa=self.empresa)
        assert pdf[:4] == b"%PDF"

    def test_gerar_sem_empresa(self):
        """Deve gerar mesmo sem dados da empresa."""
        pdf = self.service.gerar_danfse(dados=self.dados_base, empresa=None)
        assert pdf[:4] == b"%PDF"

    def test_gerar_com_descricao_longa(self):
        dados = dict(self.dados_base)
        dados["descricao_servico"] = "Prestação de serviços de desenvolvimento de software sob encomenda, " * 10
        pdf = self.service.gerar_danfse(dados=dados, empresa=self.empresa)
        assert pdf[:4] == b"%PDF"

    def test_gerar_nota_cancelada(self):
        dados = dict(self.dados_base)
        dados["situacao"] = "cancelada"
        pdf = self.service.gerar_danfse(dados=dados, empresa=self.empresa)
        assert pdf[:4] == b"%PDF"

    def test_formatar_cnpj(self):
        cnpj = self.service._formatar_cnpj("12345678000199")
        assert cnpj == "12.345.678/0001-99"

    def test_formatar_cnpj_invalido_retorna_original(self):
        cnpj = self.service._formatar_cnpj("123")
        assert cnpj == "123"

    def test_formatar_cpf(self):
        doc = self.service._formatar_doc("12345678901")
        assert doc == "123.456.789-01"

    def test_normalizar_dados_valor_total(self):
        dados_norm = self.service._normalizar_dados(self.dados_base, self.empresa)
        assert dados_norm["valor_servicos"] == 5000.0
        assert dados_norm["situacao"] == "autorizada"
        assert dados_norm["numero_nfse"] == "000001"

    def test_normalizar_dados_sem_empresa(self):
        dados_norm = self.service._normalizar_dados(self.dados_base, None)
        assert dados_norm["tomador_nome"] == "Cliente Teste Ltda"

    def test_gerar_com_ibs_cbs(self):
        """Deve incluir IBS/CBS no PDF quando presentes."""
        dados = dict(self.dados_base)
        dados["valor_ibs"] = 25.0
        dados["valor_cbs"] = 88.0
        pdf = self.service.gerar_danfse(dados=dados, empresa=self.empresa)
        assert pdf[:4] == b"%PDF"


# ============================================
# TESTES: construção XML ABRASF
# ============================================

class TestConstruirRPS:
    """Testes para construção do XML RPS (ABRASF 2.04)."""

    def setup_method(self):
        from app.services.nfse.emissao_nfse_service import EmissaoNFSeService
        self.service = EmissaoNFSeService()

        self.empresa = {
            "cnpj": "12345678000199",
            "inscricao_municipal": "12345",
            "municipio_codigo": "3550308",
        }

        self.nfse_data = {
            "numero_rps": "1",
            "serie_rps": "RPS",
            "tomador": {
                "cnpj": "98765432000100",
                "nome": "Cliente",
                "logradouro": "Rua A",
                "numero": "1",
                "bairro": "Centro",
                "codigo_municipio": "3550308",
                "uf": "SP",
                "cep": "01310100",
            },
            "servico": {
                "item_lista": "01.01",
                "discriminacao": "Serviço de TI",
            },
            "valor_servicos": "1000.00",
            "aliquota_iss": "2.00",
            "valor_iss": "20.00",
            "iss_retido": "2",
            "simples_nacional": "2",
        }

    def test_rps_xml_valido(self):
        from lxml import etree
        xml = self.service._construir_rps(self.nfse_data, self.empresa)
        assert isinstance(xml, str)
        root = etree.fromstring(xml.encode("utf-8"))
        assert root is not None

    def test_rps_contem_cnpj_prestador(self):
        xml = self.service._construir_rps(self.nfse_data, self.empresa)
        assert "12345678000199" in xml

    def test_rps_contem_numero_rps(self):
        xml = self.service._construir_rps(self.nfse_data, self.empresa)
        assert "<Numero>1</Numero>" in xml

    def test_rps_contem_discriminacao(self):
        xml = self.service._construir_rps(self.nfse_data, self.empresa)
        assert "Serviço de TI" in xml

    def test_rps_tomador_cnpj(self):
        xml = self.service._construir_rps(self.nfse_data, self.empresa)
        assert "98765432000100" in xml

    def test_rps_tomador_cpf(self):
        data = dict(self.nfse_data)
        data["tomador"] = {"cpf": "12345678901", "nome": "Pessoa Física"}
        xml = self.service._construir_rps(data, self.empresa)
        assert "12345678901" in xml

    def test_rps_versao_abrasf(self):
        xml = self.service._construir_rps(self.nfse_data, self.empresa)
        assert 'versao="2.04"' in xml


# ============================================
# TESTES: cancelamento nacional (service layer)
# ============================================

class TestCancelamentoNacional:
    """Testes para cancelamento NFS-e Nacional."""

    def setup_method(self):
        from app.services.nfse.emissao_nfse_nacional_service import NFSeNacionalService
        self.service = NFSeNacionalService()

    def test_motivo_curto_retorna_erro(self):
        import asyncio
        resultado = asyncio.get_event_loop().run_until_complete(
            self.service.cancelar_nfse(
                chave_acesso="1" * 44,
                motivo="curto",
                cert_bytes=b"fake",
                cert_password="senha",
            )
        )
        assert resultado["cancelada"] is False
        assert "15" in resultado["mensagem"]

    def test_evento_cancelamento_xml_valido(self):
        from lxml import etree
        chave = "1" * 44
        xml = self.service._montar_evento_cancelamento(chave, "Cancelamento por erro na emissão")
        root = etree.fromstring(xml.encode("utf-8"))
        assert root is not None

    def test_evento_cancelamento_contem_chave(self):
        chave = "9" * 44
        xml = self.service._montar_evento_cancelamento(chave, "Motivo de cancelamento valido aqui")
        assert chave in xml

    def test_evento_cancelamento_tipo_101(self):
        xml = self.service._montar_evento_cancelamento("1" * 44, "Motivo qualquer suficientemente longo")
        assert "<tpEvento>101</tpEvento>" in xml


# ============================================
# TESTES: sequenciamento RPS
# ============================================

class TestSequenciamentoRPS:
    """Testes para numeração automática de RPS."""

    def setup_method(self):
        from app.services.nfse.emissao_nfse_service import EmissaoNFSeService
        self.service = EmissaoNFSeService()

    @pytest.mark.asyncio
    async def test_proximo_rps_com_campo_na_empresa(self):
        """Deve incrementar numero_ultimo_rps quando campo existe."""
        db_mock = MagicMock()
        db_mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
            "numero_ultimo_rps": 5
        }
        db_mock.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        numero = await self.service._proximo_numero_rps(db_mock, "empresa-123")
        assert numero == "6"

    @pytest.mark.asyncio
    async def test_proximo_rps_fallback_por_contagem(self):
        """Deve usar contagem de notas quando campo não existe."""
        db_mock = MagicMock()
        # Simular que obter numero_ultimo_rps falha
        db_mock.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("campo não existe")
        # Contagem retorna 10 notas
        count_mock = MagicMock()
        count_mock.count = 10
        db_mock.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = count_mock

        numero = await self.service._proximo_numero_rps(db_mock, "empresa-456")
        assert numero == "11"
