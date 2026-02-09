"""
Serviço de importação de notas fiscais via Google Drive.

Fluxo:
1. Usuário autoriza via OAuth2
2. Sistema monitora pasta configurada
3. Faz scan periódico de novos XMLs
4. Importa e processa usando o mesmo pipeline do email
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from io import BytesIO

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class GoogleDriveService:
    """Serviço para integração com Google Drive."""

    _instance = None
    _fernet: Optional[Fernet] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        import os
        key = os.getenv("CERTIFICATE_ENCRYPTION_KEY")
        if key:
            try:
                self._fernet = Fernet(key.encode())
            except Exception as e:
                logger.error(f"Erro ao inicializar Fernet para Drive: {e}")

    def encrypt(self, value: str) -> str:
        if not self._fernet:
            return value
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        if not self._fernet:
            return value
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except Exception:
            return value

    # ============================================
    # OAUTH2
    # ============================================

    def gerar_url_autorizacao(self, state: Optional[str] = None) -> str:
        """Gera URL de autorização OAuth2 do Google."""
        import os

        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")

        if not client_id or not redirect_uri:
            raise ValueError(
                "GOOGLE_CLIENT_ID e GOOGLE_REDIRECT_URI devem estar configurados"
            )

        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.metadata.readonly",
        ]

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
        }

        if state:
            params["state"] = state

        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    async def processar_callback(
        self, code: str, user_id: str
    ) -> Dict[str, Any]:
        """Troca authorization code por tokens."""
        import os
        import httpx

        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

            if response.status_code != 200:
                raise ValueError(
                    f"Erro ao obter tokens: {response.text}"
                )

            tokens = response.json()

        return {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in"),
        }

    async def _refresh_token(self, config: Dict[str, Any]) -> Optional[str]:
        """Renova access token usando refresh token."""
        import os
        import httpx

        refresh_token = self.decrypt(
            config.get("oauth_refresh_token_encrypted", "")
        )
        if not refresh_token:
            return None

        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "grant_type": "refresh_token",
                },
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("access_token")

        return None

    # ============================================
    # CONFIGURAÇÃO
    # ============================================

    async def salvar_configuracao(
        self,
        user_id: str,
        dados: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Salva configuração de Google Drive."""
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()

        record = {
            "user_id": user_id,
            "provedor": "google_drive",
            "ativo": True,
        }

        if dados.get("empresa_id"):
            record["empresa_id"] = dados["empresa_id"]
        if dados.get("pasta_id"):
            record["pasta_id"] = dados["pasta_id"]
        if dados.get("pasta_nome"):
            record["pasta_nome"] = dados["pasta_nome"]

        if dados.get("access_token"):
            record["oauth_access_token_encrypted"] = self.encrypt(
                dados["access_token"]
            )
        if dados.get("refresh_token"):
            record["oauth_refresh_token_encrypted"] = self.encrypt(
                dados["refresh_token"]
            )

        if dados.get("id"):
            result = (
                db.table("configuracoes_drive")
                .update(record)
                .eq("id", dados["id"])
                .eq("user_id", user_id)
                .execute()
            )
        else:
            result = db.table("configuracoes_drive").insert(record).execute()

        if result.data:
            return result.data[0]
        raise Exception("Erro ao salvar configuração do Drive")

    async def listar_configuracoes(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        result = (
            db.table("configuracoes_drive")
            .select("id, user_id, empresa_id, provedor, pasta_id, "
                    "pasta_nome, ultima_sincronizacao, total_importadas, "
                    "ativo, created_at, updated_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def remover_configuracao(self, config_id: str, user_id: str) -> bool:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        result = (
            db.table("configuracoes_drive")
            .delete()
            .eq("id", config_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)

    # ============================================
    # LISTAR PASTAS
    # ============================================

    async def listar_pastas(self, config_id: str, user_id: str) -> List[Dict]:
        """Lista pastas do Google Drive do usuário."""
        from app.db.supabase_client import get_supabase_admin
        import httpx

        db = get_supabase_admin()
        result = (
            db.table("configuracoes_drive")
            .select("*")
            .eq("id", config_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not result.data:
            raise ValueError("Configuração não encontrada")

        config = result.data
        access_token = self.decrypt(
            config.get("oauth_access_token_encrypted", "")
        )

        if not access_token:
            access_token = await self._refresh_token(config)
            if not access_token:
                raise ValueError("Token expirado. Reautorize o Google Drive.")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/drive/v3/files",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "q": "mimeType='application/vnd.google-apps.folder' and trashed=false",
                    "fields": "files(id,name,modifiedTime)",
                    "pageSize": 100,
                },
            )
            if resp.status_code != 200:
                raise ValueError(f"Erro ao listar pastas: {resp.text}")

            data = resp.json()
            return [
                {"id": f["id"], "nome": f["name"]}
                for f in data.get("files", [])
            ]

    # ============================================
    # SINCRONIZAÇÃO
    # ============================================

    async def sincronizar(
        self, config_id: str, user_id: str
    ) -> Dict[str, Any]:
        """Sincroniza Google Drive - busca XMLs na pasta configurada."""
        from app.db.supabase_client import get_supabase_admin
        from app.services.email_import_service import email_import_service
        import httpx

        db = get_supabase_admin()

        result = (
            db.table("configuracoes_drive")
            .select("*")
            .eq("id", config_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not result.data:
            raise ValueError("Configuração não encontrada")

        config = result.data
        pasta_id = config.get("pasta_id")
        if not pasta_id:
            raise ValueError("Pasta do Drive não configurada")

        access_token = self.decrypt(
            config.get("oauth_access_token_encrypted", "")
        )
        if not access_token:
            access_token = await self._refresh_token(config)
            if not access_token:
                raise ValueError("Token expirado. Reautorize o Google Drive.")

        resumo = {
            "config_id": config_id,
            "arquivos_encontrados": 0,
            "notas_importadas": 0,
            "notas_duplicadas": 0,
            "erros": 0,
            "detalhes_erros": [],
        }

        try:
            async with httpx.AsyncClient() as client:
                # Buscar XMLs na pasta
                query = (
                    f"'{pasta_id}' in parents and "
                    f"(name contains '.xml' or mimeType='text/xml') and "
                    f"trashed=false"
                )

                resp = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "q": query,
                        "fields": "files(id,name,size,modifiedTime)",
                        "pageSize": 200,
                    },
                )

                if resp.status_code != 200:
                    raise ValueError(f"Erro ao listar arquivos: {resp.text}")

                files = resp.json().get("files", [])
                resumo["arquivos_encontrados"] = len(files)

                for f in files:
                    try:
                        # Download do arquivo
                        dl_resp = await client.get(
                            f"https://www.googleapis.com/drive/v3/files/{f['id']}",
                            headers={"Authorization": f"Bearer {access_token}"},
                            params={"alt": "media"},
                        )

                        if dl_resp.status_code != 200:
                            continue

                        xml_content = dl_resp.content

                        resultado = await email_import_service._processar_xml(
                            xml_content=xml_content,
                            filename=f["name"],
                            user_id=user_id,
                            empresa_id=config.get("empresa_id"),
                            config_id=config_id,
                            fonte="drive",
                        )

                        if resultado == "importada":
                            resumo["notas_importadas"] += 1
                        elif resultado == "duplicada":
                            resumo["notas_duplicadas"] += 1

                    except Exception as e:
                        resumo["erros"] += 1
                        resumo["detalhes_erros"].append(
                            f"{f['name']}: {str(e)}"
                        )

        except Exception as e:
            logger.error(f"Erro na sincronização Drive: {e}")
            resumo["erro_geral"] = str(e)

        # Atualizar config
        db.table("configuracoes_drive").update({
            "ultima_sincronizacao": datetime.now(timezone.utc).isoformat(),
            "total_importadas": (config.get("total_importadas", 0)
                                 + resumo["notas_importadas"]),
        }).eq("id", config_id).execute()

        return resumo


# Singleton
google_drive_service = GoogleDriveService()
