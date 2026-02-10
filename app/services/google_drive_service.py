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
    # SALVAMENTO DE XMLS NO DRIVE (BOT -> DRIVE)
    # ============================================

    async def salvar_xml_no_drive(
        self,
        empresa_id: str,
        empresa_nome: str,
        xml_content: bytes,
        nota_info: Dict[str, Any],
    ) -> Optional[str]:
        """
        Salva XML no Google Drive na estrutura:
        [Pasta Raiz] / [Nome da Empresa] / [Ano-Mes] / [Tipo] / arquivo.xml

        Verifica duplicidade antes de upload.

        Args:
            empresa_id: UUID da empresa
            empresa_nome: Razao social da empresa
            xml_content: Conteudo do XML em bytes
            nota_info: dict com 'tipo', 'numero', 'data_emissao', 'chave_acesso'

        Returns:
            file_id do Google Drive ou None se nao configurado
        """
        from app.db.supabase_client import get_supabase_admin
        import httpx

        db = get_supabase_admin()

        # 1. Buscar configuracao ativa do Drive para esta empresa
        result = (
            db.table("configuracoes_drive")
            .select("*")
            .eq("empresa_id", empresa_id)
            .eq("ativo", True)
            .limit(1)
            .execute()
        )

        if not result.data:
            logger.debug(
                f"Drive nao configurado para empresa {empresa_id}, pulando upload"
            )
            return None

        config = result.data[0]
        pasta_raiz_id = config.get("pasta_id")
        if not pasta_raiz_id:
            logger.warning(
                f"Config Drive sem pasta_id para empresa {empresa_id}"
            )
            return None

        # 2. Obter access token
        access_token = self.decrypt(
            config.get("oauth_access_token_encrypted", "")
        )
        if not access_token:
            access_token = await self._refresh_token(config)
            if not access_token:
                logger.error(
                    f"Token Drive expirado para empresa {empresa_id}"
                )
                return None

        # 3. Montar estrutura de pastas
        # Sanitizar nome da empresa para nome de pasta
        empresa_folder_name = re.sub(r'[<>:"/\\|?*]', '_', empresa_nome.strip())

        # Ano-Mes (ex: "2026-02")
        data_emissao = nota_info.get("data_emissao", "")
        if data_emissao and len(data_emissao) >= 7:
            ano_mes = data_emissao[:7]  # "YYYY-MM"
        else:
            ano_mes = datetime.now().strftime("%Y-%m")

        # Tipo: "Prestada" ou "Tomada"
        tipo_raw = nota_info.get("tipo", "NFS-e")
        if "tomad" in tipo_raw.lower():
            tipo_pasta = "Tomada"
        else:
            tipo_pasta = "Prestada"

        try:
            async with httpx.AsyncClient() as client:
                headers = {"Authorization": f"Bearer {access_token}"}

                # Criar/obter pasta da empresa
                empresa_folder_id = await self._get_or_create_folder(
                    client, headers, empresa_folder_name, pasta_raiz_id
                )

                # Criar/obter pasta do ano-mes
                mes_folder_id = await self._get_or_create_folder(
                    client, headers, ano_mes, empresa_folder_id
                )

                # Criar/obter pasta do tipo
                tipo_folder_id = await self._get_or_create_folder(
                    client, headers, tipo_pasta, mes_folder_id
                )

                # 4. Nome do arquivo
                chave = nota_info.get("chave_acesso", "")
                numero = nota_info.get("numero", "sem_numero")
                if chave:
                    filename = f"{chave}.xml"
                else:
                    filename = f"nota_{numero}_{ano_mes}.xml"

                # 5. Verificar duplicidade
                exists = await self._file_exists_in_folder(
                    client, headers, filename, tipo_folder_id
                )
                if exists:
                    logger.info(
                        f"XML ja existe no Drive: {filename} (empresa {empresa_id})"
                    )
                    return None

                # 6. Upload do XML
                file_id = await self._upload_file(
                    client, headers, filename, xml_content,
                    "text/xml", tipo_folder_id
                )

                logger.info(
                    f"XML salvo no Drive: {filename} -> {file_id} "
                    f"(empresa {empresa_id})"
                )
                return file_id

        except Exception as e:
            logger.error(
                f"Erro ao salvar XML no Drive para empresa {empresa_id}: {e}",
                exc_info=True
            )
            return None

    async def _get_or_create_folder(
        self,
        client: Any,
        headers: Dict[str, str],
        folder_name: str,
        parent_id: str,
    ) -> str:
        """Busca pasta pelo nome ou cria se nao existir."""
        # Buscar pasta existente
        query = (
            f"name='{folder_name}' and "
            f"'{parent_id}' in parents and "
            f"mimeType='application/vnd.google-apps.folder' and "
            f"trashed=false"
        )
        resp = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers=headers,
            params={"q": query, "fields": "files(id,name)", "pageSize": 1},
        )

        if resp.status_code == 200:
            files = resp.json().get("files", [])
            if files:
                return files[0]["id"]

        # Criar pasta
        import json
        metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        resp = await client.post(
            "https://www.googleapis.com/drive/v3/files",
            headers={
                **headers,
                "Content-Type": "application/json",
            },
            content=json.dumps(metadata),
            params={"fields": "id"},
        )

        if resp.status_code in (200, 201):
            return resp.json()["id"]

        raise ValueError(
            f"Erro ao criar pasta '{folder_name}': {resp.text}"
        )

    async def _file_exists_in_folder(
        self,
        client: Any,
        headers: Dict[str, str],
        filename: str,
        folder_id: str,
    ) -> bool:
        """Verifica se arquivo com mesmo nome ja existe na pasta."""
        query = (
            f"name='{filename}' and "
            f"'{folder_id}' in parents and "
            f"trashed=false"
        )
        resp = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers=headers,
            params={"q": query, "fields": "files(id)", "pageSize": 1},
        )

        if resp.status_code == 200:
            files = resp.json().get("files", [])
            return len(files) > 0

        return False

    async def _upload_file(
        self,
        client: Any,
        headers: Dict[str, str],
        filename: str,
        content: bytes,
        mime_type: str,
        parent_id: str,
    ) -> str:
        """Faz upload de arquivo para o Google Drive."""
        import json

        # Usar upload multipart simples
        boundary = "----DriveUploadBoundary"
        metadata = json.dumps({
            "name": filename,
            "parents": [parent_id],
        })

        body = (
            f"--{boundary}\r\n"
            f"Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{metadata}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode() + content + f"\r\n--{boundary}--".encode()

        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files"
            "?uploadType=multipart&fields=id",
            headers={
                **headers,
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            content=body,
        )

        if resp.status_code in (200, 201):
            return resp.json()["id"]

        raise ValueError(f"Erro no upload: {resp.text}")

    # ============================================
    # SINCRONIZAÇÃO (DRIVE -> SISTEMA)
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
