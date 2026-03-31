"""
Testes unitários para models (Pydantic)
"""
import pytest
from decimal import Decimal
from datetime import datetime, date, timedelta

from app.models.nfe_busca import (
    NFeBuscadaMetadata,
    DistribuicaoResponseModel,
    ConsultaDistribuicaoRequest,
    mapear_situacao_nfe,
    SITUACAO_NFE_MAP,
)
from app.models.nota_fiscal import (
    NotaFiscalCreate,
    NotaFiscalResponse,
    NotaFiscalSearchParams,
    BuscaNotaFilter,
)


# Chave de acesso de teste
CHAVE_TESTE = "35240112112223330001815500100000012312345671"
CNPJ_TESTE = "11222333000181"


class TestNFeBuscadaMetadata:
    """Testa o modelo NFeBuscadaMetadata"""

    def _criar_metadata_valida(self, **kwargs):
        defaults = dict(
            chave_acesso=CHAVE_TESTE,
            nsu=100,
            data_emissao=datetime(2024, 1, 15, 10, 0, 0),
            tipo_operacao="1",
            valor_total=Decimal("1000.00"),
            cnpj_emitente=CNPJ_TESTE,
            nome_emitente="Empresa Teste LTDA",
            situacao="autorizada",
            situacao_codigo="1",
        )
        defaults.update(kwargs)
        return NFeBuscadaMetadata(**defaults)

    def test_criar_metadata_valida(self):
        meta = self._criar_metadata_valida()
        assert meta.chave_acesso == CHAVE_TESTE
        assert meta.valor_total == Decimal("1000.00")

    def test_chave_acesso_invalida(self):
        with pytest.raises(Exception):
            self._criar_metadata_valida(chave_acesso="chave_curta")

    def test_chave_acesso_com_letras(self):
        with pytest.raises(Exception):
            self._criar_metadata_valida(chave_acesso="A" * 44)

    def test_tipo_operacao_invalido(self):
        with pytest.raises(Exception):
            self._criar_metadata_valida(tipo_operacao="5")

    def test_valor_negativo_invalido(self):
        with pytest.raises(Exception):
            self._criar_metadata_valida(valor_total=Decimal("-100"))

    def test_cnpj_emitente_invalido(self):
        with pytest.raises(Exception):
            self._criar_metadata_valida(cnpj_emitente="123")

    def test_cnpj_emitente_com_mascara_invalido(self):
        with pytest.raises(Exception):
            self._criar_metadata_valida(cnpj_emitente="12.345.678/0001-90")

    def test_destinatario_opcional(self):
        meta = self._criar_metadata_valida()
        assert meta.cnpj_destinatario is None
        assert meta.nome_destinatario is None

    def test_xml_resumo_opcional(self):
        meta = self._criar_metadata_valida()
        assert meta.xml_resumo is None

    def test_protocolo_opcional(self):
        meta = self._criar_metadata_valida()
        assert meta.protocolo is None


class TestDistribuicaoResponseModel:
    """Testa o modelo DistribuicaoResponseModel"""

    def _criar_response_vazia(self, status_codigo="138", **kwargs):
        defaults = dict(
            status_codigo=status_codigo,
            motivo="Sucesso",
            notas_encontradas=[],
            ultimo_nsu=0,
            max_nsu=0,
            total_notas=0,
        )
        defaults.update(kwargs)
        return DistribuicaoResponseModel(**defaults)

    def test_sucesso_com_codigo_138(self):
        response = self._criar_response_vazia(status_codigo="138")
        assert response.sucesso is True

    def test_falha_com_codigo_diferente(self):
        response = self._criar_response_vazia(status_codigo="656")
        assert response.sucesso is False

    def test_tem_mais_notas_quando_nsu_menor(self):
        response = self._criar_response_vazia(ultimo_nsu=50, max_nsu=100)
        assert response.tem_mais_notas is True

    def test_sem_mais_notas_quando_nsu_igual(self):
        response = self._criar_response_vazia(ultimo_nsu=100, max_nsu=100)
        assert response.tem_mais_notas is False

    def test_total_notas_valido(self):
        response = self._criar_response_vazia(total_notas=10)
        assert response.total_notas == 10


class TestConsultaDistribuicaoRequest:
    """Testa o modelo de request para consulta distribuição"""

    def test_cnpj_valido(self):
        req = ConsultaDistribuicaoRequest(cnpj=CNPJ_TESTE)
        assert req.cnpj == CNPJ_TESTE

    def test_cnpj_com_mascara_invalido(self):
        with pytest.raises(Exception):
            ConsultaDistribuicaoRequest(cnpj="12.345.678/0001-90")

    def test_cnpj_13_digitos_invalido(self):
        with pytest.raises(Exception):
            ConsultaDistribuicaoRequest(cnpj="1234567890123")

    def test_nsu_inicial_padrao_none(self):
        req = ConsultaDistribuicaoRequest(cnpj=CNPJ_TESTE)
        assert req.nsu_inicial is None

    def test_max_notas_padrao(self):
        req = ConsultaDistribuicaoRequest(cnpj=CNPJ_TESTE)
        assert req.max_notas == 50

    def test_max_notas_limite_superior(self):
        with pytest.raises(Exception):
            ConsultaDistribuicaoRequest(cnpj=CNPJ_TESTE, max_notas=600)

    def test_max_notas_limite_inferior(self):
        with pytest.raises(Exception):
            ConsultaDistribuicaoRequest(cnpj=CNPJ_TESTE, max_notas=0)


class TestMapearSituacaoNFe:
    """Testa a função mapear_situacao_nfe"""

    def test_codigo_1_autorizada(self):
        assert mapear_situacao_nfe("1") == "autorizada"

    def test_codigo_2_denegada(self):
        assert mapear_situacao_nfe("2") == "denegada"

    def test_codigo_3_cancelada(self):
        assert mapear_situacao_nfe("3") == "cancelada"

    def test_codigo_desconhecido(self):
        assert mapear_situacao_nfe("9") == "desconhecida"


class TestNotaFiscalCreate:
    """Testa o modelo NotaFiscalCreate"""

    def _criar_nota_valida(self, **kwargs):
        defaults = dict(
            empresa_id="empresa-uuid-123",
            numero_nf="123",
            serie="1",
            tipo_nf="NFe",
            modelo="55",
            chave_acesso=CHAVE_TESTE,
            data_emissao=datetime(2024, 1, 15, 10, 0, 0),
            valor_total=Decimal("1000.00"),
            cnpj_emitente="12345678000181",
            nome_emitente="Empresa Teste LTDA",
            situacao="autorizada",
        )
        defaults.update(kwargs)
        return NotaFiscalCreate(**defaults)

    def test_criar_nota_valida(self):
        nota = self._criar_nota_valida()
        assert nota.empresa_id == "empresa-uuid-123"
        assert nota.valor_total == Decimal("1000.00")

    def test_tipo_nf_valido(self):
        for tipo in ["NFe", "NFSe", "NFCe", "CTe"]:
            nota = self._criar_nota_valida(tipo_nf=tipo)
            assert nota.tipo_nf == tipo

    def test_tipo_nf_invalido(self):
        with pytest.raises(Exception):
            self._criar_nota_valida(tipo_nf="TipoInvalido")

    def test_cnpj_formata_automaticamente(self):
        nota = self._criar_nota_valida(cnpj_emitente="12345678000181")
        # Deve ser formatado com máscara
        assert "." in nota.cnpj_emitente or "/" in nota.cnpj_emitente

    def test_chave_acesso_invalida(self):
        with pytest.raises(Exception):
            self._criar_nota_valida(chave_acesso="chave_invalida")

    def test_valor_negativo_invalido(self):
        with pytest.raises(Exception):
            self._criar_nota_valida(valor_total=Decimal("-1"))


class TestNotaFiscalSearchParams:
    """Testa o modelo NotaFiscalSearchParams"""

    def test_params_padrao(self):
        params = NotaFiscalSearchParams()
        assert params.skip == 0
        assert params.limit == 100
        assert params.tipo_nf == "TODAS"

    def test_skip_negativo_invalido(self):
        with pytest.raises(Exception):
            NotaFiscalSearchParams(skip=-1)

    def test_limit_zero_invalido(self):
        with pytest.raises(Exception):
            NotaFiscalSearchParams(limit=0)

    def test_limit_acima_max_invalido(self):
        with pytest.raises(Exception):
            NotaFiscalSearchParams(limit=1001)

    def test_filtro_tipo_nf(self):
        params = NotaFiscalSearchParams(tipo_nf="NFe")
        assert params.tipo_nf == "NFe"


class TestBuscaNotaFilter:
    """Testa o modelo BuscaNotaFilter"""

    def test_filtro_valido(self):
        filtro = BuscaNotaFilter(
            data_inicio=date.today() - timedelta(days=30),
            data_fim=date.today() - timedelta(days=1),
        )
        assert filtro.data_inicio < filtro.data_fim

    def test_data_futura_invalida(self):
        with pytest.raises(Exception):
            BuscaNotaFilter(
                data_inicio=date.today() - timedelta(days=30),
                data_fim=date.today() + timedelta(days=1),
            )

    def test_tipo_nf_opcoes_validas(self):
        for tipo in ["NFe", "NFSe", "NFCe", "CTe"]:
            filtro = BuscaNotaFilter(
                data_inicio=date.today() - timedelta(days=30),
                data_fim=date.today() - timedelta(days=1),
                tipo_nf=tipo,
            )
            assert filtro.tipo_nf == tipo
