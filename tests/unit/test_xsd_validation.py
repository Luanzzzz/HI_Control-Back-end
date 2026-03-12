"""
Testes de validação XSD de XMLs fiscais.

Objetivo: Garantir que a validação XSD funciona corretamente
e identifica erros estruturais antes do envio ao SEFAZ.

Arquivo: backend/tests/unit/test_xsd_validation.py
"""

import pytest
from pathlib import Path

# ============================================
# FIXTURES
# ============================================

@pytest.fixture
def xml_nfe_valido():
    """
    XML de NF-e válido (modelo 55) segundo schema XSD v4.0.

    Simplificado mas com estrutura correta.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe versao="4.00" Id="NFe11111111111111111111111111111111111111111111">
    <ide>
      <cUF>35</cUF>
      <cNF>12345678</cNF>
      <natOp>Venda de Mercadoria</natOp>
      <mod>55</mod>
      <serie>1</serie>
      <nNF>123</nNF>
      <dhEmi>2026-03-12T10:00:00-03:00</dhEmi>
      <tpNF>1</tpNF>
      <idDest>1</idDest>
      <cMunFG>3550308</cMunFG>
      <tpImp>1</tpImp>
      <tpEmis>1</tpEmis>
      <cDV>0</cDV>
      <tpAmb>2</tpAmb>
      <finNFe>1</finNFe>
      <indFinal>1</indFinal>
      <indPres>1</indPres>
      <procEmi>0</procEmi>
      <verProc>1.0</verProc>
    </ide>
    <emit>
      <CNPJ>11111111000111</CNPJ>
      <xNome>Empresa Teste LTDA</xNome>
      <xFant>Empresa Teste</xFant>
      <enderEmit>
        <xLgr>Rua Principal</xLgr>
        <nro>100</nro>
        <xBairro>Centro</xBairro>
        <cMun>3550308</cMun>
        <xMun>Sao Paulo</xMun>
        <UF>SP</UF>
        <CEP>01310000</CEP>
        <cPais>1058</cPais>
        <xPais>BRASIL</xPais>
      </enderEmit>
      <IE>111111111111</IE>
      <CRT>1</CRT>
    </emit>
    <dest>
      <CPF>12345678901</CPF>
      <xNome>Cliente Teste</xNome>
      <enderDest>
        <xLgr>Av Teste</xLgr>
        <nro>200</nro>
        <xBairro>Bairro</xBairro>
        <cMun>3550308</cMun>
        <xMun>Sao Paulo</xMun>
        <UF>SP</UF>
        <CEP>01310000</CEP>
        <cPais>1058</cPais>
        <xPais>BRASIL</xPais>
      </enderDest>
      <indIEDest>9</indIEDest>
    </dest>
    <det nItem="1">
      <prod>
        <cProd>001</cProd>
        <cEAN>SEM GTIN</cEAN>
        <xProd>Produto Teste</xProd>
        <NCM>12345678</NCM>
        <CFOP>5102</CFOP>
        <uCom>UN</uCom>
        <qCom>1.0000</qCom>
        <vUnCom>100.00</vUnCom>
        <vProd>100.00</vProd>
        <cEANTrib>SEM GTIN</cEANTrib>
        <uTrib>UN</uTrib>
        <qTrib>1.0000</qTrib>
        <vUnTrib>100.00</vUnTrib>
        <indTot>1</indTot>
      </prod>
      <imposto>
        <ICMS>
          <ICMS00>
            <orig>0</orig>
            <CST>00</CST>
            <modBC>0</modBC>
            <vBC>100.00</vBC>
            <pICMS>18.00</pICMS>
            <vICMS>18.00</vICMS>
          </ICMS00>
        </ICMS>
        <PIS>
          <PISAliq>
            <CST>01</CST>
            <vBC>100.00</vBC>
            <pPIS>1.65</pPIS>
            <vPIS>1.65</vPIS>
          </PISAliq>
        </PIS>
        <COFINS>
          <COFINSAliq>
            <CST>01</CST>
            <vBC>100.00</vBC>
            <pCOFINS>7.60</pCOFINS>
            <vCOFINS>7.60</vCOFINS>
          </COFINSAliq>
        </COFINS>
      </imposto>
    </det>
    <total>
      <ICMSTot>
        <vBC>100.00</vBC>
        <vICMS>18.00</vICMS>
        <vICMSDeson>0.00</vICMSDeson>
        <vFCP>0.00</vFCP>
        <vBCST>0.00</vBCST>
        <vST>0.00</vST>
        <vFCPST>0.00</vFCPST>
        <vFCPSTRet>0.00</vFCPSTRet>
        <vProd>100.00</vProd>
        <vFrete>0.00</vFrete>
        <vSeg>0.00</vSeg>
        <vDesc>0.00</vDesc>
        <vII>0.00</vII>
        <vIPI>0.00</vIPI>
        <vIPIDevol>0.00</vIPIDevol>
        <vPIS>1.65</vPIS>
        <vCOFINS>7.60</vCOFINS>
        <vOutro>0.00</vOutro>
        <vNF>100.00</vNF>
      </ICMSTot>
    </total>
    <transp>
      <modFrete>9</modFrete>
    </transp>
    <pag>
      <detPag>
        <indPag>0</indPag>
        <tPag>01</tPag>
        <vPag>100.00</vPag>
      </detPag>
    </pag>
  </infNFe>
</NFe>"""


@pytest.fixture
def xml_nfe_campo_obrigatorio_faltando():
    """
    XML de NF-e com campo obrigatório faltando (cUF ausente).

    Deve falhar na validação XSD.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe versao="4.00" Id="NFe11111111111111111111111111111111111111111111">
    <ide>
      <!-- cUF AUSENTE (obrigatório) -->
      <cNF>12345678</cNF>
      <natOp>Venda</natOp>
      <mod>55</mod>
      <serie>1</serie>
      <nNF>123</nNF>
      <dhEmi>2026-03-12T10:00:00-03:00</dhEmi>
      <tpNF>1</tpNF>
    </ide>
  </infNFe>
</NFe>"""


@pytest.fixture
def xml_nfe_cnpj_formato_errado():
    """
    XML de NF-e com CNPJ em formato errado (com pontuação).

    CNPJ deve ter exatamente 14 dígitos numéricos.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe versao="4.00" Id="NFe11111111111111111111111111111111111111111111">
    <ide>
      <cUF>35</cUF>
      <cNF>12345678</cNF>
      <natOp>Venda</natOp>
      <mod>55</mod>
      <serie>1</serie>
      <nNF>123</nNF>
      <dhEmi>2026-03-12T10:00:00-03:00</dhEmi>
      <tpNF>1</tpNF>
    </ide>
    <emit>
      <CNPJ>11.111.111/0001-11</CNPJ>  <!-- ERRO: CNPJ com pontuação -->
      <xNome>Empresa Teste</xNome>
    </emit>
  </infNFe>
</NFe>"""


@pytest.fixture
def xml_nfe_valor_negativo():
    """
    XML de NF-e com valor negativo onde não é permitido.

    Valores de produto (vProd) devem ser >= 0.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe versao="4.00" Id="NFe11111111111111111111111111111111111111111111">
    <ide>
      <cUF>35</cUF>
      <cNF>12345678</cNF>
      <natOp>Venda</natOp>
      <mod>55</mod>
      <serie>1</serie>
      <nNF>123</nNF>
      <dhEmi>2026-03-12T10:00:00-03:00</dhEmi>
      <tpNF>1</tpNF>
    </ide>
    <det nItem="1">
      <prod>
        <cProd>001</cProd>
        <xProd>Produto</xProd>
        <NCM>12345678</NCM>
        <CFOP>5102</CFOP>
        <uCom>UN</uCom>
        <qCom>1.0000</qCom>
        <vUnCom>100.00</vUnCom>
        <vProd>-50.00</vProd>  <!-- ERRO: Valor negativo -->
      </prod>
    </det>
  </infNFe>
</NFe>"""


@pytest.fixture
def xml_mal_formado():
    """XML mal-formado (tag não fechada)."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
  <infNFe versao="4.00">
    <ide>
      <cUF>35</cUF>
      <!-- Tag não fechada abaixo -->
      <natOp>Venda
    </ide>
  </infNFe>
</NFe>"""


# ============================================
# TESTES - Verificação de schemas
# ============================================

def test_schemas_xsd_existem():
    """
    Verifica se schemas XSD oficiais estão presentes no diretório.

    Se falhar: Baixe os schemas XSD oficiais conforme instruções em:
    backend/app/schemas/xsd/README.md
    """
    schemas_dir = Path(__file__).parent.parent.parent / "app" / "schemas" / "xsd"

    # Schema principal da NF-e (CRÍTICO)
    schema_nfe = schemas_dir / "nfe_v4.00.xsd"

    if not schema_nfe.exists():
        pytest.skip(
            f"Schema XSD não encontrado: {schema_nfe}\n\n"
            f"INSTRUÇÕES:\n"
            f"1. Acesse: https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=\n"
            f"2. Baixe o pacote 'Schemas XML da NF-e versão 4.0'\n"
            f"3. Extraia os arquivos para: {schemas_dir}/\n"
            f"4. Consulte: {schemas_dir}/README.md\n\n"
            f"Este teste será PULADO até os schemas serem configurados."
        )

    # Verificar que o arquivo não está vazio
    assert schema_nfe.stat().st_size > 0, "Schema XSD está vazio"


# ============================================
# TESTES - Validação XSD
# ============================================

@pytest.mark.skipif(
    not (Path(__file__).parent.parent.parent / "app" / "schemas" / "xsd" / "nfe_v4.00.xsd").exists(),
    reason="Schema XSD não configurado (execute test_schemas_xsd_existem primeiro)"
)
def test_xml_nfe_valido_passa_validacao(xml_nfe_valido):
    """
    XML de NF-e válido DEVE passar na validação XSD.
    """
    from app.utils.xml_validator import validar_xml_nfe

    valido, erros = validar_xml_nfe(xml_nfe_valido, ambiente="development")

    assert valido is True, f"XML válido deveria passar na validação. Erros: {erros}"
    assert len(erros) == 0, f"Não deveria haver erros. Erros encontrados: {erros}"


@pytest.mark.skipif(
    not (Path(__file__).parent.parent.parent / "app" / "schemas" / "xsd" / "nfe_v4.00.xsd").exists(),
    reason="Schema XSD não configurado"
)
def test_xml_campo_obrigatorio_faltando(xml_nfe_campo_obrigatorio_faltando):
    """
    XML com campo obrigatório faltando DEVE falhar na validação.

    Deve retornar erro específico mencionando o campo ausente.
    """
    from app.utils.xml_validator import validar_xml_nfe

    valido, erros = validar_xml_nfe(xml_nfe_campo_obrigatorio_faltando, ambiente="development")

    assert valido is False, "XML com campo obrigatório faltando deveria falhar"
    assert len(erros) > 0, "Deveria retornar pelo menos 1 erro"

    # Verificar que o erro menciona o campo ausente
    erros_texto = " ".join(erros).lower()
    assert "obrigatório" in erros_texto or "required" in erros_texto, \
        f"Erro deveria mencionar campo obrigatório. Erros: {erros}"


@pytest.mark.skipif(
    not (Path(__file__).parent.parent.parent / "app" / "schemas" / "xsd" / "nfe_v4.00.xsd").exists(),
    reason="Schema XSD não configurado"
)
def test_xml_cnpj_formato_errado(xml_nfe_cnpj_formato_errado):
    """
    XML com CNPJ em formato errado (com pontuação) DEVE falhar.

    Deve retornar erro específico sobre formato de CNPJ.
    """
    from app.utils.xml_validator import validar_xml_nfe

    valido, erros = validar_xml_nfe(xml_nfe_cnpj_formato_errado, ambiente="development")

    assert valido is False, "XML com CNPJ formatado incorretamente deveria falhar"
    assert len(erros) > 0, "Deveria retornar pelo menos 1 erro"

    # Verificar que o erro menciona CNPJ
    erros_texto = " ".join(erros).lower()
    assert "cnpj" in erros_texto or "pattern" in erros_texto or "formato" in erros_texto, \
        f"Erro deveria mencionar problema com CNPJ. Erros: {erros}"


@pytest.mark.skipif(
    not (Path(__file__).parent.parent.parent / "app" / "schemas" / "xsd" / "nfe_v4.00.xsd").exists(),
    reason="Schema XSD não configurado"
)
def test_xml_valor_negativo(xml_nfe_valor_negativo):
    """
    XML com valor negativo onde não permitido DEVE falhar.

    Deve retornar erro específico sobre valor inválido.
    """
    from app.utils.xml_validator import validar_xml_nfe

    valido, erros = validar_xml_nfe(xml_nfe_valor_negativo, ambiente="development")

    assert valido is False, "XML com valor negativo deveria falhar"
    assert len(erros) > 0, "Deveria retornar pelo menos 1 erro"

    # Verificar que o erro menciona valor/produto
    erros_texto = " ".join(erros).lower()
    assert "vprod" in erros_texto or "valor" in erros_texto or "negativo" in erros_texto, \
        f"Erro deveria mencionar problema com valor. Erros: {erros}"


def test_xml_mal_formado(xml_mal_formado):
    """
    XML mal-formado (sintaxe inválida) DEVE falhar.

    Deve retornar erro de parse antes mesmo da validação XSD.
    """
    from app.utils.xml_validator import validar_xml_nfe

    valido, erros = validar_xml_nfe(xml_mal_formado, ambiente="development")

    assert valido is False, "XML mal-formado deveria falhar"
    assert len(erros) > 0, "Deveria retornar pelo menos 1 erro"

    # Verificar que o erro menciona problema de sintaxe
    erros_texto = " ".join(erros).lower()
    assert "mal-formado" in erros_texto or "linha" in erros_texto or "syntax" in erros_texto, \
        f"Erro deveria mencionar problema de sintaxe. Erros: {erros}"


# ============================================
# TESTES - Modo desenvolvimento vs produção
# ============================================

def test_desenvolvimento_sem_schema_nao_bloqueia(xml_nfe_valido):
    """
    Em desenvolvimento, AUSÊNCIA de schema XSD NÃO deve bloquear emissão.

    Deve retornar (True, []) com warning no log.
    """
    from app.utils.xml_validator import validar_xml_contra_xsd
    from unittest.mock import patch

    # Simular schema ausente (FileNotFoundError)
    with patch('app.utils.xml_validator.SCHEMAS_DIR') as mock_dir:
        mock_dir.__truediv__ = lambda self, x: Path("/caminho/inexistente")

        valido, erros = validar_xml_contra_xsd(
            xml_nfe_valido,
            tipo_documento="55",
            ambiente="development"
        )

        # Em desenvolvimento, deve permitir mesmo sem schema
        assert valido is True, "Desenvolvimento deve permitir emissão sem schema"
        assert len(erros) == 0


def test_producao_sem_schema_bloqueia(xml_nfe_valido):
    """
    Em produção, AUSÊNCIA de schema XSD DEVE bloquear emissão.

    Deve levantar FileNotFoundError.
    """
    from app.utils.xml_validator import validar_xml_contra_xsd
    from unittest.mock import patch

    # Simular schema ausente
    with patch('app.utils.xml_validator.SCHEMAS_DIR') as mock_dir:
        mock_dir.__truediv__ = lambda self, x: Path("/caminho/inexistente")

        with pytest.raises(FileNotFoundError) as exc_info:
            validar_xml_contra_xsd(
                xml_nfe_valido,
                tipo_documento="55",
                ambiente="production"
            )

        assert "Schema XSD não encontrado" in str(exc_info.value)


# ============================================
# TESTES - Atalhos de validação
# ============================================

@pytest.mark.skipif(
    not (Path(__file__).parent.parent.parent / "app" / "schemas" / "xsd" / "nfe_v4.00.xsd").exists(),
    reason="Schema XSD não configurado"
)
def test_atalho_validar_xml_nfe(xml_nfe_valido):
    """Testa atalho validar_xml_nfe()."""
    from app.utils.xml_validator import validar_xml_nfe

    valido, erros = validar_xml_nfe(xml_nfe_valido)

    assert valido is True
    assert len(erros) == 0


# ============================================
# RESUMO DE COBERTURA
# ============================================

"""
COBERTURA DE TESTES DE VALIDAÇÃO XSD:

✅ Teste 1: Schemas XSD presentes
  - test_schemas_xsd_existem() verifica configuração inicial

✅ Teste 2: XML válido passa
  - test_xml_nfe_valido_passa_validacao()

✅ Teste 3: Campo obrigatório faltando
  - test_xml_campo_obrigatorio_faltando()

✅ Teste 4: CNPJ em formato errado
  - test_xml_cnpj_formato_errado()

✅ Teste 5: Valor negativo não permitido
  - test_xml_valor_negativo()

✅ Teste 6: XML mal-formado
  - test_xml_mal_formado()

✅ Teste 7: Modo desenvolvimento permite ausência de schema
  - test_desenvolvimento_sem_schema_nao_bloqueia()

✅ Teste 8: Modo produção bloqueia ausência de schema
  - test_producao_sem_schema_bloqueia()

✅ Teste 9: Atalhos de validação
  - test_atalho_validar_xml_nfe()

RESULTADO: 9 testes criados cobrindo validação XSD completa.
"""
