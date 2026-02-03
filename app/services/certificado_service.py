"""
Serviço para gerenciamento de certificados digitais A1.

Funcionalidades:
- Upload e validação de certificados .pfx/.p12
- Criptografia segura com Fernet
- Verificação de validade e expiração
- Extração de informações do certificado
"""
import base64
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Tuple, Dict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509 import NameOID
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================
# EXCEÇÕES CUSTOMIZADAS
# ============================================

class CertificadoError(Exception):
    """Erro base para operações com certificados"""
    pass


class CertificadoInvalidoError(CertificadoError):
    """Certificado inválido ou corrompido"""
    pass


class CertificadoExpiradoError(CertificadoError):
    """Certificado fora da validade"""
    pass


class SenhaIncorretaError(CertificadoError):
    """Senha do certificado incorreta"""
    pass


# ============================================
# SERVIÇO DE CERTIFICADOS
# ============================================

class CertificadoService:
    """
    Serviço singleton para gerenciamento de certificados digitais.

    Implementa criptografia Fernet conforme decisão do usuário.
    """

    _instance = None
    _fernet: Optional[Fernet] = None

    def __new__(cls):
        """Padrão singleton"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Inicializa o serviço"""
        # Obter chave de criptografia do ambiente
        encryption_key = os.getenv("CERTIFICATE_ENCRYPTION_KEY")

        if encryption_key:
            try:
                self._fernet = Fernet(encryption_key.encode())
                logger.info("CertificadoService inicializado com Fernet encryption")
            except Exception as e:
                logger.error(f"Erro ao inicializar Fernet: {e}")
                self._fernet = None
        else:
            logger.warning(
                "CERTIFICATE_ENCRYPTION_KEY não configurada. "
                "Certificados serão armazenados apenas em base64 (menos seguro)."
            )

    # ============================================
    # VALIDAÇÃO E EXTRAÇÃO
    # ============================================

    def validar_certificado(
        self,
        cert_bytes: bytes,
        senha: str
    ) -> Dict[str, any]:
        """
        Valida certificado .pfx/.p12 e extrai informações.

        Usa cryptography.hazmat.primitives.serialization.pkcs12 (compatível
        com todas as versões modernas, sem depender de pyOpenSSL).

        Args:
            cert_bytes: Bytes do arquivo .pfx/.p12
            senha: Senha do certificado

        Returns:
            Dict com informações do certificado

        Raises:
            CertificadoInvalidoError: Se certificado inválido
            SenhaIncorretaError: Se senha incorreta
            CertificadoExpiradoError: Se certificado expirado
        """
        try:
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                cert_bytes, senha.encode()
            )
        except ValueError as e:
            error_msg = str(e).lower()
            if 'mac' in error_msg or 'password' in error_msg or 'invalid' in error_msg:
                raise SenhaIncorretaError("Senha do certificado incorreta")
            else:
                raise CertificadoInvalidoError(f"Certificado inválido: {e}")
        except Exception as e:
            raise CertificadoInvalidoError(f"Erro ao carregar certificado: {e}")

        if certificate is None:
            raise CertificadoInvalidoError("Certificado não encontrado no arquivo .pfx")

        if private_key is None:
            raise CertificadoInvalidoError("Chave privada não encontrada no certificado")

        # Extrair datas de validade
        data_inicio = certificate.not_valid_before_utc.date() if hasattr(certificate, 'not_valid_before_utc') else certificate.not_valid_before.date()
        data_fim = certificate.not_valid_after_utc.date() if hasattr(certificate, 'not_valid_after_utc') else certificate.not_valid_after.date()

        # Calcular dias restantes
        hoje = date.today()
        dias_restantes = (data_fim - hoje).days

        # Verificar validade
        if hoje < data_inicio:
            raise CertificadoInvalidoError(
                f"Certificado ainda não é válido. Validade inicia em {data_inicio}"
            )

        if hoje > data_fim:
            raise CertificadoExpiradoError(
                f"Certificado expirado em {data_fim} ({abs(dias_restantes)} dias atrás)"
            )

        # Extrair informações do titular (CN do subject)
        try:
            titular = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        except (IndexError, Exception):
            titular = "Não identificado"

        # Extrair informações do emissor (CN do issuer)
        try:
            emissor = certificate.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        except (IndexError, Exception):
            emissor = "Não identificado"

        # Serial number
        serial_number = certificate.serial_number

        logger.info(
            f"Certificado validado: Titular={titular}, "
            f"Válido até {data_fim}, {dias_restantes} dias restantes"
        )

        return {
            "valido": True,
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "dias_restantes": dias_restantes,
            "titular": titular,
            "emissor": emissor,
            "serial_number": str(serial_number),
            "requer_atencao": dias_restantes < 30,
        }

    # ============================================
    # CRIPTOGRAFIA
    # ============================================

    def criptografar_certificado(self, cert_bytes: bytes) -> str:
        """
        Criptografa certificado com Fernet e retorna base64.

        Args:
            cert_bytes: Bytes do certificado

        Returns:
            String base64 do certificado criptografado

        Raises:
            CertificadoError: Se criptografia falhar
        """
        try:
            if self._fernet:
                # Criptografar com Fernet
                encrypted = self._fernet.encrypt(cert_bytes)
                # Converter para base64 para armazenar no banco
                return base64.b64encode(encrypted).decode('utf-8')
            else:
                # Fallback: apenas base64 (menos seguro)
                logger.warning("Certificado armazenado sem criptografia Fernet")
                return base64.b64encode(cert_bytes).decode('utf-8')

        except Exception as e:
            raise CertificadoError(f"Erro ao criptografar certificado: {e}")

    def descriptografar_certificado(self, cert_base64: str) -> bytes:
        """
        Descriptografa certificado armazenado.

        Args:
            cert_base64: String base64 do certificado criptografado

        Returns:
            Bytes do certificado original

        Raises:
            CertificadoError: Se descriptografia falhar
        """
        try:
            # Decodificar base64
            encrypted_bytes = base64.b64decode(cert_base64)

            if self._fernet:
                # Descriptografar com Fernet
                try:
                    cert_bytes = self._fernet.decrypt(encrypted_bytes)
                    return cert_bytes
                except Exception as e:
                    # Pode ser certificado antigo sem Fernet, tentar direto
                    logger.warning(
                        f"Falha ao descriptografar com Fernet, "
                        f"tentando base64 direto: {e}"
                    )
                    return encrypted_bytes
            else:
                # Sem Fernet, retornar direto
                return encrypted_bytes

        except Exception as e:
            raise CertificadoError(f"Erro ao descriptografar certificado: {e}")

    # ============================================
    # OPERAÇÕES DE ALTO NÍVEL
    # ============================================

    def processar_upload(
        self,
        cert_base64_input: str,
        senha: str
    ) -> Dict[str, any]:
        """
        Processa upload de certificado: valida, criptografa e retorna info.

        Args:
            cert_base64_input: Certificado em base64 (do upload)
            senha: Senha do certificado

        Returns:
            Dict com:
            - cert_criptografado: str (para salvar no banco)
            - info: dict (informações do certificado)

        Raises:
            Exceções de validação
        """
        # Decodificar base64 de entrada
        try:
            cert_bytes = base64.b64decode(cert_base64_input)
        except Exception as e:
            raise CertificadoInvalidoError(f"Base64 inválido: {e}")

        # Validar certificado
        info = self.validar_certificado(cert_bytes, senha)

        # Criptografar para armazenamento
        cert_criptografado = self.criptografar_certificado(cert_bytes)

        return {
            "cert_criptografado": cert_criptografado,
            "info": info
        }

    def carregar_certificado(
        self,
        cert_base64_db: str,
        senha_hash: str
    ) -> Tuple[bytes, "any"]:  # type: ignore
        """
        Carrega certificado do banco para uso em assinatura.

        Args:
            cert_base64_db: Certificado criptografado do banco
            senha_hash: Hash da senha (não usado, senha vem do cache)

        Returns:
            Tupla (cert_bytes, p12_object)

        Note:
            Em produção, senha deve vir de cache seguro ou solicitada ao usuário
        """
        # Descriptografar
        cert_bytes = self.descriptografar_certificado(cert_base64_db)

        # Para uso, assumir senha em variável de ambiente ou cache
        # TODO: Implementar gestão segura de senha em produção

        return cert_bytes, None

    def verificar_expiracao(
        self,
        data_validade: date
    ) -> Dict[str, any]:
        """
        Verifica status de expiração de um certificado.

        Args:
            data_validade: Data de validade do certificado

        Returns:
            Dict com:
            - status: str (valido, expirando_em_breve, expirado, ausente)
            - dias_restantes: int
            - requer_atencao: bool
            - alerta: str (mensagem para o usuário)
        """
        if not data_validade:
            return {
                "status": "ausente",
                "dias_restantes": None,
                "requer_atencao": True,
                "alerta": "Certificado digital não cadastrado. Faça o upload para emitir NF-e."
            }

        hoje = date.today()
        dias_restantes = (data_validade - hoje).days

        if dias_restantes < 0:
            return {
                "status": "expirado",
                "dias_restantes": dias_restantes,
                "requer_atencao": True,
                "alerta": f"Certificado digital expirou há {abs(dias_restantes)} dias. Renove imediatamente."
            }
        elif dias_restantes < 30:
            return {
                "status": "expirando_em_breve",
                "dias_restantes": dias_restantes,
                "requer_atencao": True,
                "alerta": f"Certificado digital expira em {dias_restantes} dias. Renove com antecedência."
            }
        else:
            return {
                "status": "valido",
                "dias_restantes": dias_restantes,
                "requer_atencao": False,
                "alerta": f"Certificado válido até {data_validade.strftime('%d/%m/%Y')}."
            }

    # ============================================
    # UTILITÁRIOS
    # ============================================

    @staticmethod
    def gerar_chave_fernet() -> str:
        """
        Gera uma nova chave Fernet para CERTIFICATE_ENCRYPTION_KEY.

        Returns:
            Chave Fernet em string

        Usage:
            Executar uma vez e adicionar ao .env:
            >>> from app.services.certificado_service import CertificadoService
            >>> chave = CertificadoService.gerar_chave_fernet()
            >>> print(f"CERTIFICATE_ENCRYPTION_KEY={chave}")
        """
        return Fernet.generate_key().decode()

    @staticmethod
    def validar_formato_pfx(file_bytes: bytes) -> bool:
        """
        Verifica se o arquivo é um .pfx/.p12 válido.

        Args:
            file_bytes: Bytes do arquivo

        Returns:
            True se válido, False caso contrário
        """
        try:
            # Tentar carregar sem senha (falhará, mas valida formato)
            pkcs12.load_key_and_certificates(file_bytes, b'')
            return True
        except ValueError:
            # ValueError é esperado (senha incorreta), mas formato está OK
            return True
        except Exception:
            return False


# ============================================
# INSTÂNCIA SINGLETON
# ============================================

# Criar instância global para uso em toda a aplicação
certificado_service = CertificadoService()


# ============================================
# FUNÇÃO DE UTILIDADE PARA GERAÇÃO DE CHAVE
# ============================================

if __name__ == "__main__":
    """
    Executar para gerar chave Fernet:
    python -m app.services.certificado_service
    """
    print("=" * 70)
    print("Gerador de Chave Fernet para CERTIFICATE_ENCRYPTION_KEY")
    print("=" * 70)
    print()

    chave = CertificadoService.gerar_chave_fernet()

    print("Adicione esta linha ao seu arquivo backend/.env:")
    print()
    print(f"CERTIFICATE_ENCRYPTION_KEY={chave}")
    print()
    print("=" * 70)
    print("IMPORTANTE: Mantenha esta chave em segredo!")
    print("Perder esta chave significa perder acesso aos certificados armazenados.")
    print("=" * 70)
