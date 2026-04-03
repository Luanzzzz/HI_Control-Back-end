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

    SEGURANÇA (CRÍTICO):
    =====================
    A SENHA do certificado digital NÃO deve ser persistida no banco de dados.
    - Certificado (.pfx) é criptografado com Fernet e armazenado no banco
    - Senha deve ser fornecida APENAS quando necessário para operações de assinatura
    - Cada requisição de emissão (NF-e, NFC-e, CT-e) DEVE incluir a senha no request body
    - Nunca recupere a senha do campo 'certificado_senha_encrypted' do banco

    Impacto de Segurança:
    - Se o banco for comprometido, a chave Fernet vaza = todas as senhas expostas
    - Solução: Exigir que o usuário forneça a senha a cada operação
    - Trade-off: Melhor segurança vs maior atrito UX (usuário digita senha 1x por emissão)
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
                "Operações com segredos de certificados ficarão indisponíveis."
            )

    def _require_fernet(self, operation: str) -> Fernet:
        """Exige Fernet configurado para qualquer operação sensível."""
        if not self._fernet:
            raise CertificadoError(
                "CERTIFICATE_ENCRYPTION_KEY inválida ou ausente. "
                f"Não foi possível {operation}."
            )
        return self._fernet

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
            fernet = self._require_fernet("criptografar o certificado")
            encrypted = fernet.encrypt(cert_bytes)
            return base64.b64encode(encrypted).decode('utf-8')

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

            fernet = self._require_fernet("descriptografar o certificado")
            try:
                return fernet.decrypt(encrypted_bytes)
            except Exception as e:
                # Compatibilidade com registros antigos salvos sem Fernet.
                logger.warning(
                    f"Falha ao descriptografar com Fernet, usando fallback legado: {e}"
                )
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
        # Descriptografar certificado
        cert_bytes = self.descriptografar_certificado(cert_base64_db)

        # Senha agora é armazenada criptografada em certificado_senha_encrypted
        # e descriptografada via descriptografar_senha() nos endpoints de emissão

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
    # CONVERSÃO PFX → PEM PARA mTLS
    # ============================================

    def pfx_para_pem(self, pfx_bytes: bytes, senha: str) -> Tuple[bytes, bytes]:
        """
        Converte certificado .pfx (PKCS12) para par (cert.pem, key.pem).

        Necessário para uso com httpx/requests em conexões mTLS,
        pois essas bibliotecas exigem certificado e chave em formato PEM separados.

        Args:
            pfx_bytes: Bytes do arquivo .pfx/.p12
            senha: Senha do certificado

        Returns:
            Tupla (cert_pem_bytes, key_pem_bytes)
            - cert_pem_bytes: Certificado + cadeia em formato PEM
            - key_pem_bytes: Chave privada em formato PEM (sem criptografia)

        Raises:
            SenhaIncorretaError: Se senha incorreta
            CertificadoInvalidoError: Se certificado inválido
        """
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption
        )

        try:
            # Carregar certificado e chave do PFX
            private_key, certificate, additional_certs = pkcs12.load_key_and_certificates(
                pfx_bytes, senha.encode()
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

        # Converter certificado para PEM
        cert_pem = certificate.public_bytes(Encoding.PEM)

        # Adicionar certificados intermediários (cadeia completa)
        if additional_certs:
            for cert in additional_certs:
                cert_pem += cert.public_bytes(Encoding.PEM)
            logger.debug(f"Incluídos {len(additional_certs)} certificados intermediários na cadeia")

        # Converter chave privada para PEM (sem criptografia)
        # IMPORTANTE: NoEncryption() porque httpx precisa da chave sem senha
        key_pem = private_key.private_bytes(
            Encoding.PEM,
            PrivateFormat.PKCS8,
            NoEncryption()
        )

        logger.debug("Certificado convertido de PFX para PEM com sucesso")

        return cert_pem, key_pem

    # ============================================
    # UTILITÁRIOS
    # ============================================

    # SEGURANÇA: Métodos de criptografia de senha removidos (DEPRECATED)
    # A senha do certificado NÃO deve ser persistida no banco de dados.
    # Deve ser fornecida pelo usuário a cada operação de emissão.
    # Os métodos abaixo são mantidos apenas para compatibilidade com código legado.
    # IMPORTANTE: Remova qualquer referência a criptografar_senha() e descriptografar_senha()

    def criptografar_senha(self, senha: str) -> str:
        """
        DEPRECATED: Não criptografe senhas de certificado para armazenamento.

        A senha do certificado não deve ser persistida no banco.
        Este método existe apenas para compatibilidade legada.

        Args:
            senha: Senha em texto plano

        Returns:
            Senha criptografada com Fernet
        """
        logger.warning(
            "DEPRECADO: criptografar_senha() não deve ser usado. "
            "Senhas de certificado não devem ser armazenadas no banco. "
            "Forneça a senha a cada operação de emissão."
        )
        fernet = self._require_fernet("criptografar a senha do certificado")
        return fernet.encrypt(senha.encode()).decode()

    def descriptografar_senha(self, senha_encrypted: str) -> str:
        """
        DEPRECATED: Não recupere senhas de certificado do banco.

        Este método existe apenas para compatibilidade com código legado.
        A senha deve vir do request (provided by user), não do banco.

        Args:
            senha_encrypted: Senha criptografada

        Returns:
            Senha em texto plano
        """
        logger.warning(
            "DEPRECADO: descriptografar_senha() não deve ser usado. "
            "Senhas de certificado não devem ser armazenadas no banco. "
            "Recupere a senha do request do usuário."
        )
        if not senha_encrypted:
            raise CertificadoError("Senha do certificado não configurada")
        fernet = self._require_fernet("descriptografar a senha do certificado")
        try:
            return fernet.decrypt(senha_encrypted.encode()).decode()
        except Exception:
            # Compatibilidade com registros antigos salvos sem Fernet.
            return base64.b64decode(senha_encrypted).decode()

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
# EXCEÇÃO ADICIONAL PARA CERTIFICADO AUSENTE
# ============================================

class CertificadoAusenteError(CertificadoError):
    """Certificado não encontrado (empresa e contador)"""
    pass


# ============================================
# EXTENSÕES PARA ESTRATÉGIA HÍBRIDA
# ============================================

class CertificadoServiceHibrido(CertificadoService):
    """
    Extensão do CertificadoService com lógica híbrida.
    
    Prioridade:
    1. Certificado da EMPRESA (se existir e válido)
    2. Fallback: Certificado do CONTADOR (se empresa não tiver)
    """
    
    def __init__(self):
        super().__init__()
        from app.db.supabase_client import supabase_admin
        self.db = supabase_admin
    
    async def validar_status_empresa(
        self,
        empresa_id: str
    ) -> Dict[str, any]:
        """
        Valida status do certificado de uma empresa.
        
        Args:
            empresa_id: ID da empresa
        
        Returns:
            Dict com:
            - status: 'ativo' | 'vencido' | 'ausente' | 'expirando'
            - dias_para_vencer: int | None
            - data_validade: str | None
            - tem_fallback: bool (se contador tem certificado válido)
        """
        try:
            # Buscar empresa com dados de certificado
            resultado = self.db.table("empresas")\
                .select("certificado_a1, certificado_validade, usuario_id")\
                .eq("id", empresa_id)\
                .single()\
                .execute()
            
            if not resultado.data:
                return {
                    "status": "ausente",
                    "dias_para_vencer": None,
                    "data_validade": None,
                    "tem_fallback": False,
                    "mensagem": "Empresa não encontrada"
                }
            
            empresa = resultado.data
            
            # Se empresa não tem certificado
            if not empresa.get("certificado_a1"):
                # Verificar fallback do contador
                tem_fallback = await self._verificar_fallback_contador(empresa["usuario_id"])
                
                return {
                    "status": "ausente",
                    "dias_para_vencer": None,
                    "data_validade": None,
                    "tem_fallback": tem_fallback,
                    "usando_fallback": tem_fallback,
                    "mensagem": "Empresa sem certificado. " + (
                        "Usando certificado do contador." if tem_fallback 
                        else "Cadastre um certificado para buscar notas."
                    )
                }
            
            # Verificar validade do certificado da empresa
            data_validade = empresa.get("certificado_validade")
            if data_validade:
                if isinstance(data_validade, str):
                    data_validade = datetime.fromisoformat(data_validade.replace('Z', '+00:00')).date()
                
                status_exp = self.verificar_expiracao(data_validade)
                
                # Mapear status
                status_map = {
                    "valido": "ativo",
                    "expirando_em_breve": "expirando",
                    "expirado": "vencido",
                    "ausente": "ausente"
                }
                
                return {
                    "status": status_map.get(status_exp["status"], status_exp["status"]),
                    "dias_para_vencer": status_exp["dias_restantes"],
                    "data_validade": data_validade.isoformat() if data_validade else None,
                    "tem_fallback": False,
                    "usando_fallback": False,
                    "mensagem": status_exp["alerta"]
                }
            
            return {
                "status": "ausente",
                "dias_para_vencer": None,
                "data_validade": None,
                "tem_fallback": False,
                "mensagem": "Validade do certificado não informada"
            }
            
        except Exception as e:
            logger.error(f"Erro ao validar status do certificado: {e}")
            return {
                "status": "erro",
                "dias_para_vencer": None,
                "data_validade": None,
                "tem_fallback": False,
                "mensagem": f"Erro ao verificar certificado: {str(e)}"
            }
    
    async def obter_certificado_para_busca(
        self,
        empresa_id: str,
        contador_id: str
    ) -> Tuple[bytes, str, str]:
        """
        Obtém certificado para busca usando estratégia híbrida.
        
        Prioridade:
        1. Certificado da EMPRESA (se existir e válido)
        2. Fallback: Certificado do CONTADOR (se empresa não tiver)
        
        Args:
            empresa_id: ID da empresa
            contador_id: ID do contador (para fallback)
        
        Returns:
            Tupla (cert_bytes, senha, tipo_usado)
            - tipo_usado: 'empresa' | 'contador_fallback'
        
        Raises:
            CertificadoAusenteError: Se nem empresa nem contador têm certificado
            CertificadoExpiradoError: Se certificado está vencido
        """
        try:
            # 1. Tentar certificado da empresa
            empresa_cert = self.db.table("empresas")\
                .select("certificado_a1, certificado_senha_hash, certificado_validade, usuario_id")\
                .eq("id", empresa_id)\
                .single()\
                .execute()
            
            if empresa_cert.data and empresa_cert.data.get("certificado_a1"):
                # Verificar validade
                data_validade = empresa_cert.data.get("certificado_validade")
                if data_validade:
                    if isinstance(data_validade, str):
                        data_validade = datetime.fromisoformat(data_validade.replace('Z', '+00:00')).date()
                    
                    if data_validade < date.today():
                        logger.warning(f"Certificado da empresa {empresa_id} está vencido")
                        # Tentar fallback
                        return await self._tentar_fallback_contador(
                            empresa_cert.data.get("usuario_id", contador_id),
                            empresa_id
                        )
                
                # Usar certificado da empresa
                cert_bytes = self.descriptografar_certificado(
                    empresa_cert.data["certificado_a1"]
                )
                senha = empresa_cert.data.get("certificado_senha_hash", "")
                
                logger.info(f"✅ Usando certificado da EMPRESA {empresa_id}")
                return (cert_bytes, senha, "empresa")
            
            # 2. Fallback: Certificado do contador
            return await self._tentar_fallback_contador(contador_id, empresa_id)
            
        except CertificadoAusenteError:
            raise
        except CertificadoExpiradoError:
            raise
        except Exception as e:
            logger.error(f"Erro ao obter certificado: {e}")
            raise CertificadoError(f"Erro ao buscar certificado: {str(e)}")
    
    async def _tentar_fallback_contador(
        self,
        contador_id: str,
        empresa_id: str
    ) -> Tuple[bytes, str, str]:
        """
        Tenta usar certificado do contador como fallback.
        """
        try:
            contador_cert = self.db.table("usuarios")\
                .select("certificado_contador_a1, certificado_contador_validade")\
                .eq("id", contador_id)\
                .single()\
                .execute()
            
            if contador_cert.data and contador_cert.data.get("certificado_contador_a1"):
                # Verificar validade
                data_validade = contador_cert.data.get("certificado_contador_validade")
                if data_validade:
                    if isinstance(data_validade, str):
                        data_validade = datetime.fromisoformat(data_validade.replace('Z', '+00:00')).date()
                    
                    if data_validade < date.today():
                        raise CertificadoExpiradoError(
                            "Certificado do contador também está vencido. "
                            "Renove o certificado para continuar."
                        )
                
                # Usar certificado do contador
                cert_bytes = self.descriptografar_certificado(
                    contador_cert.data["certificado_contador_a1"]
                )
                
                logger.warning(
                    f"⚠️ Usando certificado do CONTADOR como fallback "
                    f"para empresa {empresa_id}"
                )
                return (cert_bytes, "", "contador_fallback")
            
            raise CertificadoAusenteError(
                "Nem a empresa nem o contador possuem certificado válido. "
                "Cadastre um certificado A1 para buscar notas fiscais."
            )
            
        except CertificadoAusenteError:
            raise
        except CertificadoExpiradoError:
            raise
        except Exception as e:
            raise CertificadoAusenteError(
                f"Erro ao buscar certificado fallback: {str(e)}"
            )
    
    async def _verificar_fallback_contador(self, contador_id: str) -> bool:
        """
        Verifica se contador tem certificado válido para fallback.
        """
        try:
            resultado = self.db.table("usuarios")\
                .select("certificado_contador_a1, certificado_contador_validade")\
                .eq("id", contador_id)\
                .single()\
                .execute()
            
            if resultado.data and resultado.data.get("certificado_contador_a1"):
                data_validade = resultado.data.get("certificado_contador_validade")
                if data_validade:
                    if isinstance(data_validade, str):
                        data_validade = datetime.fromisoformat(data_validade.replace('Z', '+00:00')).date()
                    return data_validade >= date.today()
                return True
            
            return False
        except:
            return False


# ============================================
# INSTÂNCIA SINGLETON
# ============================================

# Criar instância global para uso em toda a aplicação
certificado_service = CertificadoServiceHibrido()


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
