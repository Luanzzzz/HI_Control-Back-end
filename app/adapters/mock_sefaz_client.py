"""
Mock client para testes de DistribuicaoDFe sem certificado digital.

Este módulo fornece respostas simuladas da SEFAZ para permitir:
- Desenvolvimento local sem certificado
- Testes automatizados
- Demonstrações do sistema

NÃO USAR EM PRODUÇÃO - Apenas para desenvolvimento/testes.
"""
import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# ============================================
# XML MOCK - RESPOSTA DISTRIBUIÇÃO DFE
# ============================================

MOCK_XML_DISTRIBUICAO_SUCESSO = '''<?xml version="1.0" encoding="UTF-8"?>
<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
    <tpAmb>2</tpAmb>
    <cUF>35</cUF>
    <verAplic>SVRS20240101</verAplic>
    <cStat>138</cStat>
    <xMotivo>Documento localizado</xMotivo>
    <dhResp>2026-01-26T12:45:00-03:00</dhResp>
    <ultNSU>000000000123458</ultNSU>
    <maxNSU>000000000123460</maxNSU>
    <loteDistDFeInt>
        <docZip schema="resNFe_v1.01.xsd">
            <NSU>000000000123456</NSU>
            <resNFe versao="1.01">
                <chNFe>35260112345678000190550010000001231123456789</chNFe>
                <CNPJEmit>12345678000190</CNPJEmit>
                <xNomeEmit>EMPRESA TESTE HOMOLOGACAO LTDA</xNomeEmit>
                <IE>123456789000</IE>
                <dhEmi>2026-01-26T10:30:00-03:00</dhEmi>
                <tpNF>1</tpNF>
                <vNF>1500.00</vNF>
                <digVal>ABC123XYZ456==</digVal>
                <dhRecbto>2026-01-26T10:31:00-03:00</dhRecbto>
                <nProt>135260000123456</nProt>
                <cSitNFe>1</cSitNFe>
            </resNFe>
        </docZip>
        <docZip schema="resNFe_v1.01.xsd">
            <NSU>000000000123457</NSU>
            <resNFe versao="1.01">
                <chNFe>35260112345678000190550010000001241123456790</chNFe>
                <CNPJEmit>12345678000190</CNPJEmit>
                <xNomeEmit>EMPRESA TESTE HOMOLOGACAO LTDA</xNomeEmit>
                <IE>123456789000</IE>
                <dhEmi>2026-01-26T11:15:00-03:00</dhEmi>
                <tpNF>1</tpNF>
                <vNF>2750.50</vNF>
                <digVal>DEF789UVW123==</digVal>
                <dhRecbto>2026-01-26T11:16:00-03:00</dhRecbto>
                <nProt>135260000123457</nProt>
                <cSitNFe>1</cSitNFe>
            </resNFe>
        </docZip>
        <docZip schema="resNFe_v1.01.xsd">
            <NSU>000000000123458</NSU>
            <resNFe versao="1.01">
                <chNFe>35260112345678000190550010000001251123456791</chNFe>
                <CNPJEmit>12345678000190</CNPJEmit>
                <xNomeEmit>EMPRESA TESTE HOMOLOGACAO LTDA</xNomeEmit>
                <IE>123456789000</IE>
                <dhEmi>2026-01-25T14:20:00-03:00</dhEmi>
                <tpNF>0</tpNF>
                <vNF>890.00</vNF>
                <digVal>GHI456JKL789==</digVal>
                <dhRecbto>2026-01-25T14:21:00-03:00</dhRecbto>
                <nProt>135260000123458</nProt>
                <cSitNFe>1</cSitNFe>
            </resNFe>
        </docZip>
    </loteDistDFeInt>
</retDistDFeInt>
'''

MOCK_XML_DISTRIBUICAO_VAZIO = '''<?xml version="1.0" encoding="UTF-8"?>
<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
    <tpAmb>2</tpAmb>
    <cUF>35</cUF>
    <verAplic>SVRS20240101</verAplic>
    <cStat>137</cStat>
    <xMotivo>Nenhum documento localizado para o Destinatário</xMotivo>
    <dhResp>2026-01-26T12:45:00-03:00</dhResp>
    <ultNSU>000000000000000</ultNSU>
    <maxNSU>000000000000000</maxNSU>
</retDistDFeInt>
'''

MOCK_XML_DISTRIBUICAO_CONSUMO_INDEVIDO = '''<?xml version="1.0" encoding="UTF-8"?>
<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">
    <tpAmb>2</tpAmb>
    <cUF>35</cUF>
    <verAplic>SVRS20240101</verAplic>
    <cStat>656</cStat>
    <xMotivo>Consumo Indevido - Limite de consultas excedido</xMotivo>
    <dhResp>2026-01-26T12:45:00-03:00</dhResp>
</retDistDFeInt>
'''

# ============================================
# MOCK CLIENT
# ============================================

class MockDistribuicaoDFeClient:
    """
    Cliente mock para simular respostas da SEFAZ DistribuicaoDFe.
    
    Permite desenvolvimento e testes sem certificado digital.
    """
    
    def __init__(self):
        self.call_count = 0
        self.mode = os.getenv("MOCK_SEFAZ_MODE", "sucesso")
        logger.info(f"MockDistribuicaoDFeClient inicializado em modo: {self.mode}")
    
    def consultar(
        self, 
        cnpj: str, 
        nsu_inicial: int = 0,
        uf: str = "SP"
    ) -> str:
        """
        Simula consulta DistribuicaoDFe.
        
        Args:
            cnpj: CNPJ consultado (14 dígitos)
            nsu_inicial: NSU inicial (para paginação)
            uf: UF do CNPJ
        
        Returns:
            XML mock de resposta SEFAZ
        """
        self.call_count += 1
        
        logger.info(
            f"[MOCK] Consulta DistribuicaoDFe #{self.call_count} - "
            f"CNPJ: {cnpj}, NSU: {nsu_inicial}, UF: {uf}"
        )
        
        # Simular diferentes cenários baseado no modo
        if self.mode == "vazio":
            return MOCK_XML_DISTRIBUICAO_VAZIO
        elif self.mode == "consumo_indevido":
            return MOCK_XML_DISTRIBUICAO_CONSUMO_INDEVIDO
        elif self.mode == "erro":
            # Simular timeout/erro de rede
            raise ConnectionError("Mock: Timeout ao conectar com SEFAZ")
        else:
            # Modo sucesso (padrão)
            return MOCK_XML_DISTRIBUICAO_SUCESSO
    
    def reset(self):
        """Reseta contador de chamadas"""
        self.call_count = 0
    
    @property
    def total_calls(self) -> int:
        """Retorna total de chamadas feitas"""
        return self.call_count


# ============================================
# FACTORY FUNCTION
# ============================================

def get_distribuicao_client():
    """
    Factory para obter client de DistribuicaoDFe.
    
    Retorna mock se USE_MOCK_SEFAZ=true, caso contrário None.
    
    Returns:
        MockDistribuicaoDFeClient ou None
    """
    use_mock = os.getenv("USE_MOCK_SEFAZ", "true").lower() == "true"
    
    if use_mock:
        logger.warning("⚠️ USANDO MOCK SEFAZ - NÃO usar em produção!")
        return MockDistribuicaoDFeClient()
    
    return None


# ============================================
# HELPER - Parse resNFe do XML Mock
# ============================================

def extrair_resumos_mock(xml_response: str) -> list:
    """
    Extrai resumos de NFe do XML mock para debugging.
    
    Args:
        xml_response: XML de resposta mock
    
    Returns:
        Lista de dicts com dados dos resNFe
    """
    try:
        from lxml import etree
        
        root = etree.fromstring(xml_response.encode('utf-8'))
        namespace = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        resumos = []
        for res_nfe in root.findall('.//nfe:resNFe', namespace):
            resumos.append({
                'chave': res_nfe.findtext('.//nfe:chNFe', namespaces=namespace),
                'cnpj': res_nfe.findtext('.//nfe:CNPJ', namespaces=namespace),
                'nome': res_nfe.findtext('.//nfe:xNome', namespaces=namespace),
                'valor': res_nfe.findtext('.//nfe:vNF', namespaces=namespace),
                'nsu': res_nfe.findtext('.//nfe:NSU', default='0', namespaces=namespace),
            })
        
        return resumos
        
    except Exception as e:
        logger.error(f"Erro ao extrair resumos mock: {e}")
        return []


# ============================================
# CONFIGURAÇÃO DE AMBIENTE
# ============================================

# Variáveis de ambiente para controle do mock:
# USE_MOCK_SEFAZ=true/false - Ativa/desativa mock
# MOCK_SEFAZ_MODE=sucesso/vazio/consumo_indevido/erro - Modo de resposta

if __name__ == "__main__":
    """Teste rápido do mock client"""
    print("=" * 70)
    print("TESTE MOCK DISTRIBUIÇÃO DFE")
    print("=" * 70)
    
    client = MockDistribuicaoDFeClient()
    
    print("\n[1] Teste consulta sucesso:")
    xml = client.consultar(cnpj="12345678000190", nsu_inicial=0)
    resumos = extrair_resumos_mock(xml)
    print(f"Notas encontradas: {len(resumos)}")
    for r in resumos:
        print(f"  - {r['chave'][:10]}... | Valor: R$ {r['valor']}")
    
    print(f"\nTotal de chamadas: {client.total_calls}")
    print("=" * 70)
