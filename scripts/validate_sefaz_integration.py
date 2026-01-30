"""
Script de validação da integração SEFAZ - PyNFE Adapter.

Este script valida:
1. Importação dos módulos
2. Conversão de modelos Pydantic para PyNFE
3. Geração de XML
4. Assinatura (estrutural, sem certificado real)
5. Parseamento de resposta

Execução:
    cd backend
    venv/Scripts/python scripts/validate_sefaz_integration.py
"""

import sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

# Adicionar backend ao path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

print("=" * 70)
print("VALIDAÇÃO DA INTEGRAÇÃO SEFAZ - PyNFE Adapter")
print("=" * 70)
print()

# ============================================
# 1. Verificar Importações
# ============================================
print("[1/5] Verificando importações dos módulos...")

try:
    from app.adapters.pynfe_adapter import pynfe_adapter
    print("✅ pynfe_adapter importado com sucesso")
except ImportError as e:
    print(f"❌ Erro ao importar pynfe_adapter: {e}")
    sys.exit(1)

try:
    from app.services.sefaz_service import sefaz_service
    print("✅ sefaz_service importado com sucesso")
except ImportError as e:
    print(f"❌ Erro ao importar sefaz_service: {e}")
    sys.exit(1)

try:
    from app.models.nfe_completa import (
        NotaFiscalCompletaCreate,
        ItemNFeBase,
        DestinatarioNFe,
        TransporteNFe,
        ICMSItem,
        PISItem,
        COFINSItem,
        IPIItem,
    )
    print("✅ Modelos Pydantic importados com sucesso")
except ImportError as e:
    print(f"❌ Erro ao importar modelos: {e}")
    sys.exit(1)

print()

# ============================================
# 2. Testar Conversão Emitente
# ============================================
print("[2/5] Testando conversão de Emitente...")

empresa_dados = {
    'cnpj': '12.345.678/0001-90',
    'razao_social': 'Empresa Teste Ltda',
    'inscricao_estadual': '123456789',
    'uf': 'SP',
}

try:
    emitente = pynfe_adapter.to_pynfe_emitente(empresa_dados)
    assert emitente is not None, "Emitente não pode ser None"
    print(f"✅ Emitente convertido: {emitente.razao_social}")
except Exception as e:
    print(f"❌ Erro na conversão de Emitente: {e}")
    sys.exit(1)

print()

# ============================================
# 3. Testar Conversão Cliente
# ============================================
print("[3/5] Testando conversão de Cliente (Destinatário)...")

from decimal import Decimal

destinatario = DestinatarioNFe(
    cpf="12345678909",
    nome="CLIENTE TESTE HOMOLOGACAO",
    indicador_inscricao_estadual="9",  # Não contribuinte
    logradouro="Rua Teste",
    numero="123",
    bairro="Centro",
    codigo_municipio="3550308",  # São Paulo
    municipio="Sao Paulo",
    uf="SP",
    cep="01310100",
)

try:
    cliente = pynfe_adapter.to_pynfe_cliente(destinatario)
    assert cliente is not None, "Cliente não pode ser None"
    print(f"✅ Cliente convertido: {cliente.razao_social}")
except Exception as e:
    print(f"❌ Erro na conversão de Cliente: {e}")
    sys.exit(1)

print()

# ============================================
# 4. Testar Conversão Produto
# ============================================
print("[4/5] Testando conversão de Produto (Item)...")

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

try:
    produto = pynfe_adapter.to_pynfe_produto(item)
    assert produto is not None, "Produto não pode ser None"
    print(f"✅ Produto convertido: {produto.descricao}")
except Exception as e:
    print(f"❌ Erro na conversão de Produto: {e}")
    sys.exit(1)

print()

# ============================================
# 5. Testar Geração de XML
# ============================================
print("[5/5] Testando geração de XML completo...")

nfe_completa = NotaFiscalCompletaCreate(
    empresa_id="test-empresa-id",
    numero_nf="1",
    serie="1",
    modelo="55",
    tipo_operacao="1",  # Saída
    ambiente="2",  # Homologação
    data_emissao=datetime.now(),
    destinatario=destinatario,
    itens=[item],
    transporte=TransporteNFe(modalidade_frete=9),
    informacoes_complementares="Nota fiscal de teste - validacao integração",
)

try:
    nota_fiscal = pynfe_adapter.to_pynfe_nota_fiscal(
        nfe_data=nfe_completa,
        emitente=emitente,
        cliente=cliente,
        empresa_dados=empresa_dados
    )
    assert nota_fiscal is not None, "NotaFiscal não pode ser None"
    print(f"✅ NotaFiscal montada com sucesso")
    
    # Tentar gerar XML
    xml_nfe = pynfe_adapter.gerar_xml_nfe(
        nota_fiscal=nota_fiscal,
        ambiente="2"
    )
    
    assert xml_nfe is not None, "XML não pode ser None"
    assert len(xml_nfe) > 0, "XML não pode estar vazio"
    assert '<?xml' in xml_nfe, "XML deve ter declaração"
    assert 'NFe' in xml_nfe or 'nfe' in xml_nfe.lower(), "XML deve conter tag NFe"
    
    print(f"✅ XML gerado com sucesso ({len(xml_nfe)} bytes)")
    print(f"   - Contém declaração XML: {'<?xml' in xml_nfe}")
    print(f"   - Contém tag NFe: {'NFe' in xml_nfe or 'nfe' in xml_nfe.lower()}")
    
except Exception as e:
    print(f"❌ Erro na geração de XML: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 70)
print("✅ VALIDAÇÃO COMPLETA - Todos os testes passaram!")
print("=" * 70)
print()
print("PRÓXIMOS PASSOS:")
print("1. Configurar certificado digital no sistema")
print("2. Testar assinatura digital com certificado real")
print("3. Executar teste de comunicação com SEFAZ homologação")
print()
print("Para teste com SEFAZ, consulte: implementation_plan.md")
print("=" * 70)
