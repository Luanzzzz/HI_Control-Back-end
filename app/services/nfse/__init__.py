"""
Módulo de integração com APIs municipais de NFS-e (Nota Fiscal de Serviço Eletrônica).

Implementa o padrão Adapter para suportar múltiplos sistemas municipais:
- Sistema Nacional (ABRASF/ISSNet) - ~3.000 municípios
- Belo Horizonte/MG - API própria (BHISSDigital)
- São Paulo/SP - API própria (NFe Paulistana)

Uso:
    from app.services.nfse.nfse_service import nfse_service

    resultado = await nfse_service.buscar_notas_empresa(
        empresa_id="uuid",
        data_inicio=date(2026, 1, 1),
        data_fim=date(2026, 2, 1)
    )
"""

from app.services.nfse.base_adapter import (
    BaseNFSeAdapter,
    NFSeException,
    NFSeAuthException,
    NFSeSearchException,
    NFSeConfigException,
)
from app.services.nfse.nfse_service import NFSeService, nfse_service

__all__ = [
    "BaseNFSeAdapter",
    "NFSeException",
    "NFSeAuthException",
    "NFSeSearchException",
    "NFSeConfigException",
    "NFSeService",
    "nfse_service",
]
