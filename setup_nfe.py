"""
Hi-Control - PyNFE Setup Validation Script
Execute após instalar requirements: python setup_nfe.py

Verifica se todas as dependências necessárias para integração
com SEFAZ via PyNFE foram instaladas corretamente.
"""
import sys
from typing import Dict, List, Tuple


def check_dependencies() -> Tuple[bool, List[str]]:
    """
    Verifica se todas as dependências NFe foram instaladas.

    Returns:
        Tuple[bool, List[str]]: (sucesso, lista de pacotes ausentes)
    """

    required: Dict[str, str] = {
        'lxml': 'Parsing XML',
        'signxml': 'Assinatura digital',
        'OpenSSL': 'Certificados (via pyOpenSSL)',
        'nfe': 'PyNFe core',
        'validate_docbr': 'Validação CNPJ/CPF',
        'zeep': 'SOAP SEFAZ',
        'defusedxml': 'XML seguro',
        'oscrypto': 'Certificados A1',
    }

    print("🔍 Verificando dependências NFe...")
    print("=" * 70)

    missing: List[str] = []

    for package, description in required.items():
        try:
            __import__(package)
            print(f"✅ {package:20} - {description}")
        except ImportError:
            print(f"❌ {package:20} - {description} [AUSENTE]")
            missing.append(package)

    print("=" * 70)

    if missing:
        print(f"\n❌ {len(missing)} dependência(s) faltando!")
        print("Execute: pip install -r requirements.txt")
        return False, missing
    else:
        print("\n✅ Todas as dependências instaladas!")
        return True, []


def test_xml_parsing() -> bool:
    """
    Testa parsing básico de XML com lxml.

    Returns:
        bool: True se parsing funcionou, False caso contrário
    """
    try:
        from lxml import etree

        # XML de teste simulando estrutura NF-e
        xml_test = """<?xml version="1.0" encoding="UTF-8"?>
        <NFe xmlns="http://www.portalfiscal.inf.br/nfe">
            <infNFe Id="NFe35240112345678000190550010000001231234567890">
                <ide>
                    <cUF>35</cUF>
                    <mod>55</mod>
                </ide>
            </infNFe>
        </NFe>"""

        # Parse XML
        root = etree.fromstring(xml_test.encode())

        # Verifica se conseguiu parsear namespace
        namespaces = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        mod = root.find('.//nfe:mod', namespaces)

        if mod is not None and mod.text == '55':
            print("✅ Parsing XML: OK")
            return True
        else:
            print("❌ Parsing XML: Falha ao ler elementos")
            return False

    except Exception as e:
        print(f"❌ Parsing XML: {e}")
        return False


def test_certificate_handling() -> bool:
    """
    Testa manipulação de certificados com pyOpenSSL.

    Returns:
        bool: True se manipulação funcionou, False caso contrário
    """
    try:
        from OpenSSL import crypto
        from datetime import datetime

        # Testa criação de certificado auto-assinado (apenas teste)
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 2048)

        cert = crypto.X509()
        cert.get_subject().C = "BR"
        cert.get_subject().ST = "SP"
        cert.get_subject().L = "São Paulo"
        cert.get_subject().O = "Hi-Control Test"
        cert.get_subject().CN = "Test Certificate"
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)  # 1 ano
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, 'sha256')

        # Verifica se consegue exportar para PEM
        pem = crypto.dump_certificate(crypto.FILETYPE_PEM, cert)

        if pem and len(pem) > 0:
            print("✅ Manipulação de certificados: OK")
            return True
        else:
            print("❌ Manipulação de certificados: Falha na exportação")
            return False

    except Exception as e:
        print(f"❌ Manipulação de certificados: {e}")
        return False


def test_cpf_cnpj_validation() -> bool:
    """
    Testa validação de CPF/CNPJ com validate-docbr.

    Returns:
        bool: True se validação funcionou, False caso contrário
    """
    try:
        from validate_docbr import CNPJ, CPF

        cnpj_validator = CNPJ()
        cpf_validator = CPF()

        # Testa CNPJ válido (número de teste)
        cnpj_valido = "11222333000181"
        cnpj_invalido = "12345678901234"

        # Testa CPF válido (número de teste)
        cpf_valido = "11144477735"
        cpf_invalido = "12345678901"

        # Validações
        checks = [
            cnpj_validator.validate(cnpj_valido) is True,
            cnpj_validator.validate(cnpj_invalido) is False,
            cpf_validator.validate(cpf_valido) is True,
            cpf_validator.validate(cpf_invalido) is False,
        ]

        if all(checks):
            print("✅ Validação CPF/CNPJ: OK")
            return True
        else:
            print("❌ Validação CPF/CNPJ: Falha nos testes")
            return False

    except Exception as e:
        print(f"❌ Validação CPF/CNPJ: {e}")
        return False


def test_cryptography_version() -> bool:
    """
    Verifica se a versão do cryptography é compatível com PyNFE.

    Returns:
        bool: True se versão correta, False caso contrário
    """
    try:
        import cryptography
        from packaging import version

        current = version.parse(cryptography.__version__)
        required = version.parse("42.0.0")
        max_version = version.parse("43.0.0")

        if required <= current < max_version:
            print(f"✅ Cryptography version {current}: OK (compatível com PyNFE)")
            return True
        else:
            print(f"⚠️  Cryptography version {current}: Esperado 42.x.x")
            print("   Execute: pip install cryptography==42.0.0")
            return False

    except Exception as e:
        print(f"❌ Verificação cryptography: {e}")
        return False


def main():
    """Executa todos os testes de validação."""

    print("\n" + "=" * 70)
    print("🚀 Hi-Control - Validação de Setup PyNFe")
    print("=" * 70 + "\n")

    # Teste 1: Dependências
    deps_ok, missing = check_dependencies()

    if not deps_ok:
        print("\n" + "=" * 70)
        print("❌ FALHA: Dependências ausentes")
        print("=" * 70)
        print("\nPacotes faltando:")
        for pkg in missing:
            print(f"  - {pkg}")
        print("\nExecute: pip install -r requirements.txt")
        sys.exit(1)

    # Teste 2: Funcionalidades
    print("\n🧪 Testando funcionalidades...\n")

    tests = [
        ("Cryptography Version", test_cryptography_version),
        ("XML Parsing", test_xml_parsing),
        ("Certificados", test_certificate_handling),
        ("CPF/CNPJ Validation", test_cpf_cnpj_validation),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Erro em '{test_name}': {e}")
            results.append((test_name, False))

    # Resultado final
    print("\n" + "=" * 70)

    failed_tests = [name for name, result in results if not result]

    if not failed_tests:
        print("✅ AMBIENTE PRONTO PARA INTEGRAÇÃO PyNFe")
        print("=" * 70)
        print("\nPróximos passos:")
        print("1. Configure CERTIFICATE_ENCRYPTION_KEY no .env")
        print("2. Execute as migrações de banco de dados")
        print("3. Implemente os serviços SEFAZ")
        print("\nDocumentação: README.md")
        sys.exit(0)
    else:
        print("❌ AMBIENTE NÃO ESTÁ PRONTO")
        print("=" * 70)
        print(f"\n{len(failed_tests)} teste(s) falharam:")
        for test_name in failed_tests:
            print(f"  - {test_name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
