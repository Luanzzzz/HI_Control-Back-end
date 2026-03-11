"""
Utilitário para carregar e descriptografar certificados

Seguindo padrões MCP: operações seguras e error handling robusto.
"""

import base64
import logging
from typing import Optional, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.serialization import pkcs12

from bot.config import config

logger = logging.getLogger(__name__)


class CertificadoLoader:
    """
    Carrega e descriptografa certificados A1 para uso no bot.
    
    Seguindo padrões MCP: operações seguras com error handling.
    """
    
    _fernet: Optional[Fernet] = None
    
    @classmethod
    def _get_fernet(cls) -> Optional[Fernet]:
        """Obtém instância Fernet para descriptografia."""
        if cls._fernet is None and config.CERTIFICATE_ENCRYPTION_KEY:
            try:
                cls._fernet = Fernet(config.CERTIFICATE_ENCRYPTION_KEY.encode())
            except Exception as e:
                logger.error(f"Erro ao inicializar Fernet: {e}")
        return cls._fernet
    
    @classmethod
    def descriptografar_certificado(cls, cert_base64_encrypted: str) -> bytes:
        """
        Descriptografa certificado do banco.
        
        Args:
            cert_base64_encrypted: Certificado criptografado em base64
            
        Returns:
            Bytes do certificado descriptografado
            
        Raises:
            ValueError: Se descriptografia falhar
        """
        try:
            fernet = cls._get_fernet()
            
            if fernet:
                # Descriptografar com Fernet
                cert_bytes = fernet.decrypt(cert_base64_encrypted.encode())
            else:
                # Fallback: assumir que está apenas em base64
                cert_bytes = base64.b64decode(cert_base64_encrypted)
            
            return cert_bytes
            
        except Exception as e:
            logger.error(f"Erro ao descriptografar certificado: {e}")
            raise ValueError(f"Falha ao descriptografar certificado: {e}")
    
    @classmethod
    def descriptografar_senha(cls, senha_encrypted: str) -> str:
        """
        Descriptografa senha do certificado.
        
        Args:
            senha_encrypted: Senha criptografada
            
        Returns:
            Senha descriptografada
        """
        try:
            fernet = cls._get_fernet()
            
            if fernet:
                return fernet.decrypt(senha_encrypted.encode()).decode()
            else:
                # Fallback: assumir que não está criptografada
                return senha_encrypted
                
        except Exception as e:
            logger.warning(f"Erro ao descriptografar senha: {e}")
            # Tentar usar como está (pode não estar criptografada)
            return senha_encrypted
    
    @classmethod
    def carregar_certificado_empresa(
        cls,
        cert_base64: str,
        senha_encrypted: str
    ) -> Tuple[bytes, str]:
        """
        Carrega certificado completo da empresa.
        
        Args:
            cert_base64: Certificado criptografado em base64
            senha_encrypted: Senha criptografada
            
        Returns:
            Tupla (cert_bytes, senha)
        """
        cert_bytes = cls.descriptografar_certificado(cert_base64)
        senha = cls.descriptografar_senha(senha_encrypted)
        
        return cert_bytes, senha
