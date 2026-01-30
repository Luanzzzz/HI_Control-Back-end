"""
Dados mockados para desenvolvimento e testes
TODO: Substituir por integração real com python-nfe e Portal Nacional
"""
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List
import uuid

from app.models.nota_fiscal import NotaFiscalResponse


def gerar_notas_mock() -> List[NotaFiscalResponse]:
    """
    Gera lista de notas fiscais mockadas para testes

    Returns:
        Lista de NotaFiscalResponse com dados fictícios
    """
    base_date = datetime.now() - timedelta(days=30)

    notas_mock = [
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000123",
            "serie": "1",
            "tipo_nf": "NFe",
            "modelo": "55",
            "chave_acesso": "35240112345678000190550010000001231000000001",
            "data_emissao": base_date + timedelta(days=1, hours=10),
            "data_autorizacao": base_date + timedelta(days=1, hours=10, minutes=15),
            "valor_total": Decimal("5400.00"),
            "valor_produtos": Decimal("5000.00"),
            "valor_servicos": None,
            "cnpj_emitente": "12.345.678/0001-90",
            "nome_emitente": "Tech Solutions Ltda",
            "cnpj_destinatario": "98.765.432/0001-11",
            "nome_destinatario": "Cliente ABC Comércio",
            "situacao": "autorizada",
            "protocolo": "135240000123456",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": "Nota fiscal de venda de equipamentos",
            "created_at": base_date + timedelta(days=1),
            "updated_at": base_date + timedelta(days=1),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000124",
            "serie": "1",
            "tipo_nf": "NFCe",
            "modelo": "65",
            "chave_acesso": "35240198765432000111650010000001241000000002",
            "data_emissao": base_date + timedelta(days=2, hours=14),
            "data_autorizacao": base_date + timedelta(days=2, hours=14, minutes=5),
            "valor_total": Decimal("2150.00"),
            "valor_produtos": Decimal("2150.00"),
            "valor_servicos": None,
            "cnpj_emitente": "98.765.432/0001-11",
            "nome_emitente": "Mercado Silva & Cia",
            "cnpj_destinatario": None,
            "nome_destinatario": "Consumidor Final",
            "situacao": "autorizada",
            "protocolo": "135240000123457",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": None,
            "created_at": base_date + timedelta(days=2),
            "updated_at": base_date + timedelta(days=2),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000125",
            "serie": "2",
            "tipo_nf": "NFe",
            "modelo": "55",
            "chave_acesso": "35240111222333000144550020000001251000000003",
            "data_emissao": base_date + timedelta(days=3, hours=9),
            "data_autorizacao": None,
            "valor_total": Decimal("8900.00"),
            "valor_produtos": Decimal("8500.00"),
            "valor_servicos": None,
            "cnpj_emitente": "11.222.333/0001-44",
            "nome_emitente": "Consultório Médico Dra. Ana",
            "cnpj_destinatario": "45.678.901/0001-23",
            "nome_destinatario": "Hospital Central",
            "situacao": "cancelada",
            "protocolo": "135240000123458",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": "Cancelada a pedido do cliente",
            "created_at": base_date + timedelta(days=3),
            "updated_at": base_date + timedelta(days=3, hours=2),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000126",
            "serie": "1",
            "tipo_nf": "NFSe",
            "modelo": None,
            "chave_acesso": None,
            "data_emissao": base_date + timedelta(days=5, hours=11),
            "data_autorizacao": base_date + timedelta(days=5, hours=11, minutes=30),
            "valor_total": Decimal("3200.00"),
            "valor_produtos": None,
            "valor_servicos": Decimal("3200.00"),
            "cnpj_emitente": "22.333.444/0001-55",
            "nome_emitente": "Consultoria TI Smart",
            "cnpj_destinatario": "12.345.678/0001-90",
            "nome_destinatario": "Tech Solutions Ltda",
            "situacao": "autorizada",
            "protocolo": "NFS20240001234",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": "Serviços de consultoria em TI",
            "created_at": base_date + timedelta(days=5),
            "updated_at": base_date + timedelta(days=5),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000127",
            "serie": "1",
            "tipo_nf": "CTe",
            "modelo": "57",
            "chave_acesso": "35240156789012000177570010000001271000000004",
            "data_emissao": base_date + timedelta(days=7, hours=8),
            "data_autorizacao": base_date + timedelta(days=7, hours=8, minutes=20),
            "valor_total": Decimal("1850.00"),
            "valor_produtos": None,
            "valor_servicos": Decimal("1850.00"),
            "cnpj_emitente": "56.789.012/0001-77",
            "nome_emitente": "Transportadora Rápida Ltda",
            "cnpj_destinatario": "12.345.678/0001-90",
            "nome_destinatario": "Tech Solutions Ltda",
            "situacao": "autorizada",
            "protocolo": "135240000123459",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": "Transporte de mercadorias",
            "created_at": base_date + timedelta(days=7),
            "updated_at": base_date + timedelta(days=7),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000128",
            "serie": "1",
            "tipo_nf": "NFe",
            "modelo": "55",
            "chave_acesso": "35240112345678000190550010000001281000000005",
            "data_emissao": base_date + timedelta(days=10, hours=15),
            "data_autorizacao": None,
            "valor_total": Decimal("12500.00"),
            "valor_produtos": Decimal("12000.00"),
            "valor_servicos": None,
            "cnpj_emitente": "12.345.678/0001-90",
            "nome_emitente": "Tech Solutions Ltda",
            "cnpj_destinatario": "33.444.555/0001-66",
            "nome_destinatario": "Indústria XYZ S.A.",
            "situacao": "processando",
            "protocolo": None,
            "xml_url": None,
            "pdf_url": None,
            "observacoes": "Aguardando autorização SEFAZ",
            "created_at": base_date + timedelta(days=10),
            "updated_at": base_date + timedelta(days=10),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000129",
            "serie": "3",
            "tipo_nf": "NFe",
            "modelo": "55",
            "chave_acesso": "35240199887766000155550030000001291000000006",
            "data_emissao": base_date + timedelta(days=12, hours=13),
            "data_autorizacao": None,
            "valor_total": Decimal("7650.00"),
            "valor_produtos": Decimal("7200.00"),
            "valor_servicos": None,
            "cnpj_emitente": "99.887.766/0001-55",
            "nome_emitente": "Distribuidora Nacional",
            "cnpj_destinatario": "12.345.678/0001-90",
            "nome_destinatario": "Tech Solutions Ltda",
            "situacao": "denegada",
            "protocolo": "135240000123460",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": "Denegada por irregularidade cadastral",
            "created_at": base_date + timedelta(days=12),
            "updated_at": base_date + timedelta(days=12, hours=1),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000130",
            "serie": "1",
            "tipo_nf": "NFe",
            "modelo": "55",
            "chave_acesso": "35240112345678000190550010000001301000000007",
            "data_emissao": base_date + timedelta(days=15, hours=16),
            "data_autorizacao": base_date + timedelta(days=15, hours=16, minutes=10),
            "valor_total": Decimal("4320.00"),
            "valor_produtos": Decimal("4000.00"),
            "valor_servicos": None,
            "cnpj_emitente": "12.345.678/0001-90",
            "nome_emitente": "Tech Solutions Ltda",
            "cnpj_destinatario": "77.888.999/0001-00",
            "nome_destinatario": "Comércio Alfa Beta",
            "situacao": "autorizada",
            "protocolo": "135240000123461",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": None,
            "created_at": base_date + timedelta(days=15),
            "updated_at": base_date + timedelta(days=15),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000131",
            "serie": "1",
            "tipo_nf": "NFCe",
            "modelo": "65",
            "chave_acesso": "35240198765432000111650010000001311000000008",
            "data_emissao": base_date + timedelta(days=18, hours=12),
            "data_autorizacao": base_date + timedelta(days=18, hours=12, minutes=3),
            "valor_total": Decimal("685.50"),
            "valor_produtos": Decimal("685.50"),
            "valor_servicos": None,
            "cnpj_emitente": "98.765.432/0001-11",
            "nome_emitente": "Mercado Silva & Cia",
            "cnpj_destinatario": None,
            "nome_destinatario": "Consumidor Final",
            "situacao": "autorizada",
            "protocolo": "135240000123462",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": None,
            "created_at": base_date + timedelta(days=18),
            "updated_at": base_date + timedelta(days=18),
            "deleted_at": None
        },
        {
            "id": str(uuid.uuid4()),
            "empresa_id": str(uuid.uuid4()),
            "numero_nf": "000000132",
            "serie": "1",
            "tipo_nf": "NFSe",
            "modelo": None,
            "chave_acesso": None,
            "data_emissao": base_date + timedelta(days=20, hours=14),
            "data_autorizacao": base_date + timedelta(days=20, hours=14, minutes=25),
            "valor_total": Decimal("5600.00"),
            "valor_produtos": None,
            "valor_servicos": Decimal("5600.00"),
            "cnpj_emitente": "22.333.444/0001-55",
            "nome_emitente": "Consultoria TI Smart",
            "cnpj_destinatario": "99.887.766/0001-55",
            "nome_destinatario": "Distribuidora Nacional",
            "situacao": "autorizada",
            "protocolo": "NFS20240001235",
            "xml_url": None,
            "pdf_url": None,
            "observacoes": "Consultoria em implementação de ERP",
            "created_at": base_date + timedelta(days=20),
            "updated_at": base_date + timedelta(days=20),
            "deleted_at": None
        }
    ]

    return [NotaFiscalResponse(**nota) for nota in notas_mock]


# Cache global de notas mock (simula banco de dados em memória)
_NOTAS_MOCK_CACHE: List[NotaFiscalResponse] = []


def get_notas_mock() -> List[NotaFiscalResponse]:
    """
    Retorna lista de notas mock (usa cache para consistência)

    Returns:
        Lista de notas fiscais mockadas
    """
    global _NOTAS_MOCK_CACHE

    if not _NOTAS_MOCK_CACHE:
        _NOTAS_MOCK_CACHE = gerar_notas_mock()

    return _NOTAS_MOCK_CACHE


def reset_notas_mock():
    """Reseta o cache de notas mock (útil para testes)"""
    global _NOTAS_MOCK_CACHE
    _NOTAS_MOCK_CACHE = []
