"""
Testes unitários para services/nfe_mapper.py
"""
import pytest
from decimal import Decimal
from datetime import datetime

from app.services.nfe_mapper import (
    extrair_numero_da_chave,
    extrair_serie_da_chave,
    extrair_uf_da_chave,
    extrair_modelo_da_chave,
    modelo_to_tipo_nf,
    gerar_id_from_chave,
    validar_chave_acesso,
    map_nfe_buscada_to_nota_fiscal,
)
from app.models.nfe_busca import NFeBuscadaMetadata


# Chave de teste válida: SP, 2024/12, CNPJ 11222333000181, modelo 55, série 001, nNF 000000123
# Posições SEFAZ: [0:2]=UF, [2:8]=AAMM, [8:22]=CNPJ, [22:24]=modelo, [24:27]=série, [27:36]=número
CHAVE_TESTE = "35240112112223330001815500100000012312345671"


class TestExtrairNumeroDaChave:
    def test_extrair_numero_basico(self):
        # Posições 25-33 = número da nota
        # CHAVE_TESTE[25:34] = "000000123" -> "123"
        resultado = extrair_numero_da_chave(CHAVE_TESTE)
        assert resultado == "123"

    def test_extrair_numero_sem_zeros_esquerda(self):
        chave = "35240112345678000181550010000001231234567890"
        resultado = extrair_numero_da_chave(chave)
        assert not resultado.startswith("0")

    def test_extrair_numero_chave_valida(self):
        resultado = extrair_numero_da_chave(CHAVE_TESTE)
        assert resultado.isdigit()


class TestExtrairSerieDaChave:
    def test_extrair_serie(self):
        # Posições 22-24 = série
        # CHAVE_TESTE[22:25] = "001" -> "1"
        resultado = extrair_serie_da_chave(CHAVE_TESTE)
        assert resultado == "1"

    def test_extrair_serie_sem_zeros(self):
        resultado = extrair_serie_da_chave(CHAVE_TESTE)
        assert not resultado.startswith("0") or resultado == "0"


class TestExtrairUFDaChave:
    def test_extrair_uf_sp(self):
        resultado = extrair_uf_da_chave(CHAVE_TESTE)
        assert resultado == "35"  # SP

    def test_extrair_uf_rj(self):
        chave_rj = "33" + CHAVE_TESTE[2:]
        resultado = extrair_uf_da_chave(chave_rj)
        assert resultado == "33"  # RJ


class TestExtrairModeloDaChave:
    def test_extrair_modelo_55_nfe(self):
        # CHAVE_TESTE[22:24] = "55" (posição SEFAZ correta)
        resultado = extrair_modelo_da_chave(CHAVE_TESTE)
        assert resultado == "55"

    def test_extrair_modelo_65_nfce(self):
        chave_nfce = CHAVE_TESTE[:22] + "65" + CHAVE_TESTE[24:]
        resultado = extrair_modelo_da_chave(chave_nfce)
        assert resultado == "65"

    def test_chave_invalida_levanta_erro(self):
        with pytest.raises(ValueError):
            extrair_modelo_da_chave("chave_curta")

    def test_chave_vazia_levanta_erro(self):
        with pytest.raises(ValueError):
            extrair_modelo_da_chave("")


class TestModeloToTipoNF:
    def test_nfe_entrada(self):
        resultado = modelo_to_tipo_nf("55", "entrada")
        assert "NFe" in resultado
        assert "Entrada" in resultado

    def test_nfce_saida(self):
        resultado = modelo_to_tipo_nf("65", "saida")
        assert "NFCe" in resultado
        assert "Saida" in resultado

    def test_cte(self):
        resultado = modelo_to_tipo_nf("57", "entrada")
        assert "CT-e" in resultado

    def test_modelo_desconhecido(self):
        resultado = modelo_to_tipo_nf("99", "saida")
        assert "99" in resultado


class TestGerarIdFromChave:
    def test_gerar_id_retorna_12_digitos(self):
        resultado = gerar_id_from_chave(CHAVE_TESTE)
        assert len(resultado) == 12

    def test_gerar_id_chave_invalida_retorna_original(self):
        chave_invalida = "abc"
        resultado = gerar_id_from_chave(chave_invalida)
        assert resultado == chave_invalida

    def test_gerar_id_ultimos_12(self):
        resultado = gerar_id_from_chave(CHAVE_TESTE)
        assert resultado == CHAVE_TESTE[-12:]


class TestValidarChaveAcesso:
    def test_chave_valida(self):
        assert validar_chave_acesso(CHAVE_TESTE) is True

    def test_chave_curta(self):
        assert validar_chave_acesso("12345") is False

    def test_chave_com_letras(self):
        assert validar_chave_acesso("A" + CHAVE_TESTE[1:]) is False

    def test_chave_vazia(self):
        assert validar_chave_acesso("") is False

    def test_chave_none(self):
        assert validar_chave_acesso(None) is False


class TestMapNfeBuscadaToNotaFiscal:
    """Testes para o mapeamento de NFeBuscadaMetadata para NotaFiscalCreate"""

    @pytest.fixture
    def nfe_metadata(self):
        return NFeBuscadaMetadata(
            chave_acesso=CHAVE_TESTE,
            nsu=12345,
            data_emissao=datetime(2024, 1, 15, 10, 30, 0),
            tipo_operacao="1",
            valor_total=Decimal("1500.00"),
            cnpj_emitente="11222333000181",
            nome_emitente="Empresa Teste LTDA",
            situacao="autorizada",
            situacao_codigo="1",
        )

    def test_mapeamento_basico(self, nfe_metadata):
        nota = map_nfe_buscada_to_nota_fiscal(nfe_metadata, "empresa-uuid-123")
        assert nota.empresa_id == "empresa-uuid-123"
        assert nota.chave_acesso == CHAVE_TESTE
        assert nota.valor_total == Decimal("1500.00")

    def test_mapeamento_situacao_autorizada(self, nfe_metadata):
        nota = map_nfe_buscada_to_nota_fiscal(nfe_metadata, "empresa-uuid-123")
        assert nota.situacao == "autorizada"

    def test_mapeamento_situacao_cancelada(self, nfe_metadata):
        nfe_metadata.situacao_codigo = "3"
        nota = map_nfe_buscada_to_nota_fiscal(nfe_metadata, "empresa-uuid-123")
        assert nota.situacao == "cancelada"

    def test_mapeamento_situacao_denegada(self, nfe_metadata):
        nfe_metadata.situacao_codigo = "2"
        nota = map_nfe_buscada_to_nota_fiscal(nfe_metadata, "empresa-uuid-123")
        assert nota.situacao == "denegada"

    def test_chave_invalida_levanta_erro(self):
        # map_nfe_buscada_to_nota_fiscal valida o tamanho da chave diretamente
        # NFeBuscadaMetadata valida no __init__ (len=44, isdigit), então
        # testamos o mapper diretamente com um objeto com chave manipulada
        from app.models.nfe_busca import NFeBuscadaMetadata
        from decimal import Decimal
        from datetime import datetime
        meta = NFeBuscadaMetadata(
            chave_acesso=CHAVE_TESTE,
            nsu=1,
            data_emissao=datetime(2024, 1, 1),
            tipo_operacao="1",
            valor_total=Decimal("100"),
            cnpj_emitente="11222333000181",
            nome_emitente="Teste",
            situacao="autorizada",
            situacao_codigo="1",
        )
        meta.chave_acesso = "chave_curta"  # Burla validação pós-init
        with pytest.raises(ValueError):
            map_nfe_buscada_to_nota_fiscal(meta, "empresa-uuid-123")

    def test_mapeamento_numero_e_serie(self, nfe_metadata):
        nota = map_nfe_buscada_to_nota_fiscal(nfe_metadata, "empresa-uuid-123")
        assert nota.numero_nf == "123"
        assert nota.serie == "1"
