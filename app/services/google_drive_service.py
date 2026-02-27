"""
Serviço de importação de notas fiscais via Google Drive.

Fluxo:
1. Usuário autoriza via OAuth2
2. Sistema monitora pasta configurada
3. Faz scan periódico de novos XMLs
4. Importa e processa usando o mesmo pipeline do email
"""
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class GoogleDriveService:
    """Serviço para integração com Google Drive."""

    _instance = None
    _fernet: Optional[Fernet] = None
    _export_tasks: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        key = os.getenv("CERTIFICATE_ENCRYPTION_KEY")
        if key:
            try:
                self._fernet = Fernet(key.encode())
            except Exception as e:
                logger.error(f"Erro ao inicializar Fernet para Drive: {e}")

    def _obter_scopes_oauth(self) -> List[str]:
        """
        Resolve scopes OAuth para o Google Drive.

        Usa GOOGLE_DRIVE_OAUTH_SCOPES (csv) quando definido.
        Fallback inclui escrita para exportacao em massa.
        """
        custom_scopes = str(os.getenv("GOOGLE_DRIVE_OAUTH_SCOPES", "") or "").strip()
        if custom_scopes:
            scopes = [scope.strip() for scope in custom_scopes.split(",") if scope.strip()]
            if scopes:
                return scopes

        return [
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.metadata.readonly",
        ]

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
        client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "")

        if not client_id or not redirect_uri:
            raise ValueError(
                "GOOGLE_CLIENT_ID e GOOGLE_REDIRECT_URI devem estar configurados"
            )

        scopes = self._obter_scopes_oauth()

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
            .select(
                "id, user_id, empresa_id, provedor, pasta_id, "
                "pasta_nome, pasta_raiz_export_id, pasta_raiz_export_nome, "
                "ultima_sincronizacao, total_importadas, ativo, created_at, updated_at"
            )
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

    async def obter_configuracao_ativa(
        self,
        user_id: str,
        empresa_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve configuracao de Drive ativa para o usuario.

        Prioridade:
        1) config vinculada a empresa_id (quando informado)
        2) config global (empresa_id nulo)
        3) primeira configuracao ativa disponivel
        """
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        result = (
            db.table("configuracoes_drive")
            .select("*")
            .eq("user_id", user_id)
            .eq("ativo", True)
            .order("created_at", desc=False)
            .execute()
        )
        rows = result.data or []
        if not rows:
            return None

        if empresa_id:
            for row in rows:
                if str(row.get("empresa_id") or "") == str(empresa_id):
                    return row

        for row in rows:
            if not row.get("empresa_id"):
                return row

        return rows[0]

    async def _persistir_access_token(
        self,
        config_id: str,
        access_token: str,
    ) -> None:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        try:
            db.table("configuracoes_drive").update(
                {"oauth_access_token_encrypted": self.encrypt(access_token)}
            ).eq("id", config_id).execute()
        except Exception:
            logger.debug("Falha ao persistir access token renovado do Google Drive.", exc_info=True)

    async def obter_access_token_config(self, config: Dict[str, Any]) -> str:
        access_token = self.decrypt(config.get("oauth_access_token_encrypted", ""))
        if access_token:
            return access_token

        access_token = await self._refresh_token(config)
        if not access_token:
            raise ValueError("Token expirado. Reautorize o Google Drive.")

        config_id = str(config.get("id") or "")
        if config_id:
            await self._persistir_access_token(config_id, access_token)

        return access_token

    def _escape_drive_query_value(self, value: str) -> str:
        return str(value or "").replace("\\", "\\\\").replace("'", "\\'")

    def _sanitize_folder_name(self, value: str, fallback: str = "Pasta") -> str:
        texto = str(value or "").strip()
        if not texto:
            texto = fallback
        texto = re.sub(r'[<>:"/\\|?*]+', "_", texto)
        texto = re.sub(r"\s+", " ", texto).strip().rstrip(".")
        return (texto or fallback)[:120]

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
        access_token = await self.obter_access_token_config(config)

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

        empresa_resp = (
            db.table("empresas")
            .select("id, usuario_id")
            .eq("id", empresa_id)
            .limit(1)
            .execute()
        )
        if not empresa_resp.data:
            logger.warning("Empresa nao encontrada ao tentar salvar XML no Drive: %s", empresa_id)
            return None

        usuario_id = str(empresa_resp.data[0].get("usuario_id") or "")
        if not usuario_id:
            logger.warning("Empresa sem usuario_id ao salvar XML no Drive: %s", empresa_id)
            return None

        # 1. Buscar configuracao ativa (empresa ou global do contador)
        config = await self.obter_configuracao_ativa(usuario_id, empresa_id=empresa_id)
        if not config:
            logger.debug(
                f"Drive nao configurado para empresa {empresa_id}, pulando upload"
            )
            return None

        pasta_raiz_id = config.get("pasta_raiz_export_id") or config.get("pasta_id")
        if not pasta_raiz_id:
            try:
                pasta_raiz = await self.garantir_pasta_raiz_exportacao(
                    user_id=usuario_id,
                    config=config,
                )
                pasta_raiz_id = pasta_raiz.get("pasta_raiz_id")
            except Exception:
                logger.exception("Falha ao garantir pasta raiz no Drive para empresa %s", empresa_id)
                return None

        # 2. Obter access token
        try:
            access_token = await self.obter_access_token_config(config)
        except Exception:
            logger.error("Token Drive expirado para empresa %s", empresa_id)
            return None

        # 3. Montar estrutura de pastas
        # Sanitizar nome da empresa para nome de pasta
        empresa_folder_name = self._sanitize_folder_name(empresa_nome, fallback="Empresa")

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
        folder_name = self._sanitize_folder_name(folder_name, fallback="Pasta")
        folder_name_query = self._escape_drive_query_value(folder_name)
        parent_query = self._escape_drive_query_value(parent_id)

        # Buscar pasta existente
        query = (
            f"name='{folder_name_query}' and "
            f"'{parent_query}' in parents and "
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
        filename_query = self._escape_drive_query_value(filename)
        folder_query = self._escape_drive_query_value(folder_id)
        query = (
            f"name='{filename_query}' and "
            f"'{folder_query}' in parents and "
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

    async def _obter_arquivo_por_nome_em_pasta(
        self,
        client: Any,
        headers: Dict[str, str],
        filename: str,
        folder_id: str,
    ) -> Optional[str]:
        """Retorna o file_id do primeiro arquivo encontrado com mesmo nome na pasta."""
        filename_query = self._escape_drive_query_value(filename)
        folder_query = self._escape_drive_query_value(folder_id)
        query = (
            f"name='{filename_query}' and "
            f"'{folder_query}' in parents and "
            f"trashed=false"
        )
        resp = await client.get(
            "https://www.googleapis.com/drive/v3/files",
            headers=headers,
            params={"q": query, "fields": "files(id,name)", "pageSize": 1},
        )
        if resp.status_code != 200:
            return None
        files = resp.json().get("files", [])
        if not files:
            return None
        return str(files[0].get("id") or "")

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

    async def garantir_pasta_raiz_exportacao(
        self,
        *,
        user_id: str,
        config: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, str]:
        """Garante pasta raiz de exportacao no Drive e persiste na configuracao."""
        from app.db.supabase_client import get_supabase_admin
        import httpx

        db = get_supabase_admin()
        cfg = config or await self.obter_configuracao_ativa(user_id)
        if not cfg:
            raise ValueError("Google Drive nao conectado para este usuario.")

        token = access_token or await self.obter_access_token_config(cfg)
        headers = {"Authorization": f"Bearer {token}"}

        root_name = self._sanitize_folder_name(
            str(
                cfg.get("pasta_raiz_export_nome")
                or os.getenv("GOOGLE_DRIVE_EXPORT_ROOT_FOLDER", "Hi-Control Exportacoes")
            ),
            fallback="Hi-Control Exportacoes",
        )
        root_id = str(cfg.get("pasta_raiz_export_id") or "").strip()

        async with httpx.AsyncClient(timeout=30.0) as client:
            if root_id:
                check_resp = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{root_id}",
                    headers=headers,
                    params={"fields": "id,name,mimeType,trashed"},
                )
                if check_resp.status_code == 200:
                    payload = check_resp.json()
                    if payload.get("mimeType") == "application/vnd.google-apps.folder" and not payload.get("trashed"):
                        root_name = str(payload.get("name") or root_name)
                    else:
                        root_id = ""
                else:
                    root_id = ""

            if not root_id:
                root_id = await self._get_or_create_folder(client, headers, root_name, "root")

        if (
            root_id != str(cfg.get("pasta_raiz_export_id") or "")
            or root_name != str(cfg.get("pasta_raiz_export_nome") or "")
        ):
            db.table("configuracoes_drive").update(
                {
                    "pasta_raiz_export_id": root_id,
                    "pasta_raiz_export_nome": root_name,
                }
            ).eq("id", cfg["id"]).execute()

        return {
            "config_id": str(cfg["id"]),
            "pasta_raiz_id": root_id,
            "pasta_raiz_nome": root_name,
            "access_token": token,
        }

    async def sincronizar_pastas_clientes(
        self,
        *,
        user_id: str,
        empresa_ids: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cria/garante estrutura de pastas por cliente:
        [Pasta Raiz]/[CNPJ - Razao Social]
        """
        from app.db.supabase_client import get_supabase_admin
        import httpx

        db = get_supabase_admin()
        raiz = await self.garantir_pasta_raiz_exportacao(
            user_id=user_id,
            config=config,
            access_token=access_token,
        )
        token = raiz["access_token"]
        root_id = raiz["pasta_raiz_id"]

        query = (
            db.table("empresas")
            .select("id, cnpj, razao_social")
            .eq("usuario_id", user_id)
            .is_("deleted_at", "null")
        )
        if empresa_ids:
            query = query.in_("id", [str(eid) for eid in empresa_ids])

        empresas = query.execute().data or []
        headers = {"Authorization": f"Bearer {token}"}
        mapeadas: List[Dict[str, Any]] = []
        criadas = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            for empresa in empresas:
                empresa_id = str(empresa.get("id") or "")
                if not empresa_id:
                    continue

                cnpj_digits = re.sub(r"\D", "", str(empresa.get("cnpj") or ""))
                nome_empresa = str(empresa.get("razao_social") or "Empresa")
                nome_pasta = self._sanitize_folder_name(
                    f"{cnpj_digits or 'SEM-CNPJ'} - {nome_empresa}",
                    fallback=nome_empresa,
                )

                pasta_empresa_id = await self._get_or_create_folder(
                    client,
                    headers,
                    nome_pasta,
                    root_id,
                )

                existente = (
                    db.table("drive_pastas_empresas")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("empresa_id", empresa_id)
                    .limit(1)
                    .execute()
                )

                payload = {
                    "user_id": user_id,
                    "empresa_id": empresa_id,
                    "pasta_raiz_id": root_id,
                    "pasta_empresa_id": pasta_empresa_id,
                    "pasta_empresa_nome": nome_pasta,
                    "criado_automaticamente": True,
                    "ativo": True,
                }

                if existente.data:
                    db.table("drive_pastas_empresas").update(payload).eq("id", existente.data[0]["id"]).execute()
                else:
                    db.table("drive_pastas_empresas").insert(payload).execute()
                    criadas += 1

                mapeadas.append(payload)

        return {
            "pasta_raiz_id": root_id,
            "pasta_raiz_nome": raiz["pasta_raiz_nome"],
            "total_empresas": len(mapeadas),
            "pastas_criadas": criadas,
            "mapeamentos": mapeadas,
        }

    def _normalizar_mes_referencia(self, data_emissao: Any) -> str:
        valor = str(data_emissao or "").strip()
        if len(valor) >= 7:
            return valor[:7]
        return datetime.now().strftime("%Y-%m")

    def _montar_nome_arquivo_xml(self, nota: Dict[str, Any], mes_ref: str) -> str:
        chave = re.sub(r"\s+", "", str(nota.get("chave_acesso") or ""))
        numero = self._sanitize_folder_name(str(nota.get("numero_nf") or "sem-numero"), fallback="sem-numero")
        tipo_nf = self._sanitize_folder_name(str(nota.get("tipo_nf") or "NF"), fallback="NF")
        if chave:
            return f"{tipo_nf}_{chave}.xml"
        return f"{tipo_nf}_{numero}_{mes_ref}.xml"

    async def _atualizar_job_exportacao(self, job_id: str, campos: Dict[str, Any]) -> None:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        db.table("drive_export_jobs").update(campos).eq("id", job_id).execute()

    async def _registrar_item_exportacao(
        self,
        *,
        job_id: str,
        user_id: str,
        empresa_id: str,
        nota: Dict[str, Any],
        status_item: str,
        mensagem: Optional[str] = None,
        arquivo_nome: Optional[str] = None,
        pasta_destino_id: Optional[str] = None,
        drive_file_id: Optional[str] = None,
    ) -> None:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        nota_id = str(nota.get("id") or "")
        payload = {
            "job_id": job_id,
            "user_id": user_id,
            "empresa_id": empresa_id,
            "nota_id": nota_id if nota_id else None,
            "chave_acesso": nota.get("chave_acesso"),
            "numero_nf": str(nota.get("numero_nf") or ""),
            "mes_referencia": self._normalizar_mes_referencia(nota.get("data_emissao")),
            "tipo_operacao": nota.get("tipo_operacao"),
            "arquivo_nome": arquivo_nome or "",
            "pasta_destino_id": pasta_destino_id,
            "drive_file_id": drive_file_id,
            "status": status_item,
            "mensagem": mensagem,
        }

        existente = (
            db.table("drive_export_job_itens")
            .select("id")
            .eq("job_id", job_id)
            .eq("nota_id", payload["nota_id"])
            .limit(1)
            .execute()
        )
        if existente.data:
            db.table("drive_export_job_itens").update(payload).eq("id", existente.data[0]["id"]).execute()
        else:
            db.table("drive_export_job_itens").insert(payload).execute()

    def _aplicar_filtros_exportacao_notas(
        self,
        query: Any,
        filtros: Dict[str, Any],
    ) -> Any:
        data_inicio = str(filtros.get("data_inicio") or "").strip()
        data_fim = str(filtros.get("data_fim") or "").strip()
        status = str(filtros.get("status") or "").strip().lower()
        busca = str(filtros.get("busca") or "").strip()
        tipo = str(filtros.get("tipo") or "").strip()

        if data_inicio:
            query = query.gte("data_emissao", f"{data_inicio}T00:00:00")
        if data_fim:
            query = query.lte("data_emissao", f"{data_fim}T23:59:59")

        if status and status not in {"todos", "todas"}:
            if status == "ativa":
                query = query.eq("situacao", "autorizada")
            else:
                query = query.eq("situacao", status)

        if tipo and tipo.lower() not in {"todos", "todas"}:
            tipo_map = {
                "nfe": "NFe",
                "nfse": "NFSe",
                "nfce": "NFCe",
                "cte": "CTe",
            }
            query = query.eq("tipo_nf", tipo_map.get(tipo.replace("-", "").lower(), tipo))

        if busca:
            termo = busca.replace("'", "")
            query = query.or_(
                ",".join(
                    [
                        f"numero_nf.ilike.%{termo}%",
                        f"chave_acesso.ilike.%{termo}%",
                        f"nome_emitente.ilike.%{termo}%",
                        f"nome_destinatario.ilike.%{termo}%",
                        f"cnpj_emitente.ilike.%{termo}%",
                        f"cnpj_destinatario.ilike.%{termo}%",
                    ]
                )
            )

        incluir_tomadas = bool(filtros.get("incluir_tomadas", True))
        incluir_prestadas = bool(filtros.get("incluir_prestadas", True))
        if incluir_tomadas and not incluir_prestadas:
            query = query.eq("tipo_operacao", "entrada")
        elif incluir_prestadas and not incluir_tomadas:
            query = query.eq("tipo_operacao", "saida")

        return query

    async def iniciar_exportacao_xml_massa(
        self,
        *,
        user_id: str,
        empresa_ids: Optional[List[str]] = None,
        filtros: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from app.db.supabase_client import get_supabase_admin
        import asyncio

        db = get_supabase_admin()
        filtros = filtros or {}
        empresa_ids_norm = [str(item) for item in (empresa_ids or []) if str(item).strip()]

        config = await self.obter_configuracao_ativa(user_id)
        if not config:
            raise ValueError("Google Drive nao conectado. Conecte o Drive antes de exportar.")

        root_info = await self.garantir_pasta_raiz_exportacao(user_id=user_id, config=config)
        await self.sincronizar_pastas_clientes(
            user_id=user_id,
            empresa_ids=empresa_ids_norm or None,
            config=config,
            access_token=root_info["access_token"],
        )

        empresas_query = (
            db.table("empresas")
            .select("id")
            .eq("usuario_id", user_id)
            .is_("deleted_at", "null")
        )
        if empresa_ids_norm:
            empresas_query = empresas_query.in_("id", empresa_ids_norm)
        empresas = empresas_query.execute().data or []
        empresa_ids_job = [str(row.get("id")) for row in empresas if row.get("id")]
        if not empresa_ids_job:
            raise ValueError("Nenhuma empresa encontrada para exportacao.")

        total_estimado = 0
        for empresa_id in empresa_ids_job:
            count_query = (
                db.table("notas_fiscais")
                .select("id", count="exact")
                .eq("empresa_id", empresa_id)
            )
            count_query = self._aplicar_filtros_exportacao_notas(count_query, filtros)
            count_resp = count_query.limit(1).execute()
            total_estimado += int(count_resp.count or 0)

        job_payload = {
            "user_id": user_id,
            "config_drive_id": config["id"],
            "status": "pendente",
            "empresa_ids": empresa_ids_job,
            "filtros": filtros,
            "total_notas": total_estimado,
            "notas_processadas": 0,
            "notas_exportadas": 0,
            "notas_duplicadas": 0,
            "notas_erro": 0,
            "progresso_percentual": 0,
            "mensagem": "Exportacao enfileirada...",
            "pasta_raiz_id": root_info["pasta_raiz_id"],
        }

        job_resp = db.table("drive_export_jobs").insert(job_payload).execute()
        if not job_resp.data:
            raise ValueError("Nao foi possivel criar job de exportacao.")

        job = job_resp.data[0]
        job_id = str(job["id"])
        task = asyncio.create_task(self._executar_exportacao_job(job_id))
        self._export_tasks[job_id] = task

        def _cleanup_task(_task: Any) -> None:
            self._export_tasks.pop(job_id, None)

        task.add_done_callback(_cleanup_task)
        return job

    async def obter_status_exportacao(self, *, job_id: str, user_id: str) -> Dict[str, Any]:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        resp = (
            db.table("drive_export_jobs")
            .select("*")
            .eq("id", job_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not resp.data:
            raise ValueError("Job de exportacao nao encontrado.")
        job = resp.data[0]
        job["em_execucao"] = bool(self._export_tasks.get(job_id))
        return job

    async def listar_exportacoes(self, *, user_id: str, limite: int = 20) -> List[Dict[str, Any]]:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        resp = (
            db.table("drive_export_jobs")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(max(1, min(100, int(limite))))
            .execute()
        )
        return resp.data or []

    async def _executar_exportacao_job(self, job_id: str) -> None:
        from app.db.supabase_client import get_supabase_admin
        import httpx

        db = get_supabase_admin()

        try:
            job_resp = db.table("drive_export_jobs").select("*").eq("id", job_id).limit(1).execute()
            if not job_resp.data:
                return
            job = job_resp.data[0]
            user_id = str(job.get("user_id") or "")
            filtros = dict(job.get("filtros") or {})
            empresa_ids = [str(item) for item in (job.get("empresa_ids") or []) if str(item)]
            if not user_id or not empresa_ids:
                await self._atualizar_job_exportacao(
                    job_id,
                    {
                        "status": "erro",
                        "mensagem": "Job invalido sem usuario/empresas.",
                        "finalizado_em": datetime.now(timezone.utc).isoformat(),
                    },
                )
                return

            config = await self.obter_configuracao_ativa(user_id)
            if not config:
                await self._atualizar_job_exportacao(
                    job_id,
                    {
                        "status": "erro",
                        "mensagem": "Google Drive nao conectado.",
                        "finalizado_em": datetime.now(timezone.utc).isoformat(),
                    },
                )
                return

            root_info = await self.garantir_pasta_raiz_exportacao(user_id=user_id, config=config)
            token = root_info["access_token"]
            sync_result = await self.sincronizar_pastas_clientes(
                user_id=user_id,
                empresa_ids=empresa_ids,
                config=config,
                access_token=token,
            )

            mapeamentos = {
                str(item["empresa_id"]): item
                for item in (sync_result.get("mapeamentos") or [])
                if item.get("empresa_id")
            }

            await self._atualizar_job_exportacao(
                job_id,
                {
                    "status": "processando",
                    "iniciado_em": datetime.now(timezone.utc).isoformat(),
                    "mensagem": "Iniciando upload dos XMLs para Google Drive...",
                    "progresso_percentual": 0,
                },
            )

            totais = {
                "processadas": 0,
                "exportadas": 0,
                "duplicadas": 0,
                "erros": 0,
            }
            total_notas = int(job.get("total_notas") or 0)
            sobrescrever = bool(filtros.get("sobrescrever_arquivos", False))
            organizar_por_mes = bool(filtros.get("organizar_por_mes", True))
            separar_por_operacao = bool(filtros.get("separar_por_operacao", True))

            headers = {"Authorization": f"Bearer {token}"}
            month_folder_cache: Dict[str, str] = {}

            async with httpx.AsyncClient(timeout=60.0) as client:
                for empresa_id in empresa_ids:
                    pasta_empresa = mapeamentos.get(empresa_id)
                    if not pasta_empresa:
                        totais["erros"] += 1
                        continue

                    empresa_folder_id = str(pasta_empresa.get("pasta_empresa_id") or "")
                    if not empresa_folder_id:
                        totais["erros"] += 1
                        continue

                    offset = 0
                    page_size = 200

                    while True:
                        query = (
                            db.table("notas_fiscais")
                            .select(
                                "id, chave_acesso, numero_nf, tipo_nf, tipo_operacao, data_emissao, "
                                "xml_completo, xml_resumo"
                            )
                            .eq("empresa_id", empresa_id)
                        )
                        query = self._aplicar_filtros_exportacao_notas(query, filtros)
                        query = query.order("data_emissao", desc=True).range(offset, offset + page_size - 1)
                        notas_page = query.execute().data or []
                        if not notas_page:
                            break

                        for nota in notas_page:
                            totais["processadas"] += 1
                            mes_ref = self._normalizar_mes_referencia(nota.get("data_emissao"))
                            arquivo_nome = self._montar_nome_arquivo_xml(nota, mes_ref)

                            parent_folder_id = empresa_folder_id
                            if organizar_por_mes:
                                mes_cache_key = f"{empresa_id}:{mes_ref}"
                                if mes_cache_key not in month_folder_cache:
                                    month_folder_cache[mes_cache_key] = await self._get_or_create_folder(
                                        client,
                                        headers,
                                        mes_ref,
                                        empresa_folder_id,
                                    )
                                parent_folder_id = month_folder_cache[mes_cache_key]

                            if separar_por_operacao:
                                op_nome = "Prestadas" if str(nota.get("tipo_operacao") or "entrada") == "saida" else "Tomadas"
                                op_cache_key = f"{empresa_id}:{mes_ref}:{op_nome}"
                                if op_cache_key not in month_folder_cache:
                                    month_folder_cache[op_cache_key] = await self._get_or_create_folder(
                                        client,
                                        headers,
                                        op_nome,
                                        parent_folder_id,
                                    )
                                parent_folder_id = month_folder_cache[op_cache_key]

                            xml_text = str(nota.get("xml_completo") or nota.get("xml_resumo") or "").strip()
                            if not xml_text:
                                totais["erros"] += 1
                                await self._registrar_item_exportacao(
                                    job_id=job_id,
                                    user_id=user_id,
                                    empresa_id=empresa_id,
                                    nota=nota,
                                    status_item="erro",
                                    mensagem="Nota sem XML completo/resumo para exportacao.",
                                    arquivo_nome=arquivo_nome,
                                    pasta_destino_id=parent_folder_id,
                                )
                                continue

                            existente_id = await self._obter_arquivo_por_nome_em_pasta(
                                client,
                                headers,
                                arquivo_nome,
                                parent_folder_id,
                            )
                            if existente_id and not sobrescrever:
                                totais["duplicadas"] += 1
                                await self._registrar_item_exportacao(
                                    job_id=job_id,
                                    user_id=user_id,
                                    empresa_id=empresa_id,
                                    nota=nota,
                                    status_item="duplicada",
                                    mensagem="Arquivo ja existente no Drive.",
                                    arquivo_nome=arquivo_nome,
                                    pasta_destino_id=parent_folder_id,
                                    drive_file_id=existente_id,
                                )
                                continue

                            if existente_id and sobrescrever:
                                try:
                                    await client.delete(
                                        f"https://www.googleapis.com/drive/v3/files/{existente_id}",
                                        headers=headers,
                                    )
                                except Exception:
                                    logger.debug("Falha ao remover arquivo existente para sobrescrita.", exc_info=True)

                            try:
                                file_id = await self._upload_file(
                                    client,
                                    headers,
                                    arquivo_nome,
                                    xml_text.encode("utf-8"),
                                    "application/xml",
                                    parent_folder_id,
                                )
                                totais["exportadas"] += 1
                                await self._registrar_item_exportacao(
                                    job_id=job_id,
                                    user_id=user_id,
                                    empresa_id=empresa_id,
                                    nota=nota,
                                    status_item="exportada",
                                    arquivo_nome=arquivo_nome,
                                    pasta_destino_id=parent_folder_id,
                                    drive_file_id=file_id,
                                )
                            except Exception as exc:  # noqa: BLE001
                                totais["erros"] += 1
                                await self._registrar_item_exportacao(
                                    job_id=job_id,
                                    user_id=user_id,
                                    empresa_id=empresa_id,
                                    nota=nota,
                                    status_item="erro",
                                    mensagem=f"Falha upload: {exc}",
                                    arquivo_nome=arquivo_nome,
                                    pasta_destino_id=parent_folder_id,
                                )

                            if total_notas > 0:
                                progresso = round((totais["processadas"] / total_notas) * 100, 2)
                            else:
                                progresso = 0

                            if totais["processadas"] % 15 == 0:
                                await self._atualizar_job_exportacao(
                                    job_id,
                                    {
                                        "notas_processadas": totais["processadas"],
                                        "notas_exportadas": totais["exportadas"],
                                        "notas_duplicadas": totais["duplicadas"],
                                        "notas_erro": totais["erros"],
                                        "progresso_percentual": progresso,
                                        "mensagem": f"Exportando XMLs... {totais['processadas']} processadas",
                                    },
                                )

                        offset += len(notas_page)

            status_final = "concluido"
            if totais["erros"] > 0:
                status_final = "concluido_com_erros" if totais["exportadas"] > 0 else "erro"

            progresso_final = 100 if total_notas > 0 else (100 if totais["processadas"] > 0 else 0)
            await self._atualizar_job_exportacao(
                job_id,
                {
                    "status": status_final,
                    "notas_processadas": totais["processadas"],
                    "notas_exportadas": totais["exportadas"],
                    "notas_duplicadas": totais["duplicadas"],
                    "notas_erro": totais["erros"],
                    "progresso_percentual": progresso_final,
                    "mensagem": (
                        f"Exportacao finalizada: {totais['exportadas']} exportadas, "
                        f"{totais['duplicadas']} duplicadas, {totais['erros']} erros."
                    ),
                    "finalizado_em": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro geral no job de exportacao Google Drive job_id=%s", job_id)
            await self._atualizar_job_exportacao(
                job_id,
                {
                    "status": "erro",
                    "mensagem": f"Erro geral na exportacao: {exc}",
                    "finalizado_em": datetime.now(timezone.utc).isoformat(),
                },
            )

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


    # ============================================
    # LEITURA DIRETA DE XMLS (SEM IMPORTAR)
    # ============================================

    async def listar_e_parsear_xmls(
        self,
        config: Dict[str, Any],
        limite: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Lista XMLs do Drive e parseia sem salvar no banco.

        Args:
            config: Configuração do Drive com tokens
            limite: Máximo de arquivos a processar

        Returns:
            Lista de dicts com dados das notas parseadas
        """
        import httpx
        import xml.etree.ElementTree as ET

        pasta_id = config.get("pasta_id")
        if not pasta_id:
            return []

        # Obter access token
        access_token = self.decrypt(
            config.get("oauth_access_token_encrypted", "")
        )
        if not access_token:
            access_token = await self._refresh_token(config)
            if not access_token:
                raise ValueError("Token Drive expirado")

        notas = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Buscar XMLs recursivamente (inclui subpastas)
            query = (
                f"('{pasta_id}' in parents or "
                f"'{pasta_id}' in ancestors) and "
                f"(name contains '.xml' or mimeType='text/xml') and "
                f"trashed=false"
            )

            # Fallback: buscar apenas na pasta raiz se ancestors falhar
            try:
                resp = await client.get(
                    "https://www.googleapis.com/drive/v3/files",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={
                        "q": query,
                        "fields": "files(id,name,size,modifiedTime,parents)",
                        "pageSize": limite,
                        "orderBy": "modifiedTime desc",
                    },
                )
            except Exception:
                # Fallback para busca simples
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
                        "fields": "files(id,name,size,modifiedTime,parents)",
                        "pageSize": limite,
                        "orderBy": "modifiedTime desc",
                    },
                )

            if resp.status_code != 200:
                raise ValueError(f"Erro ao listar arquivos: {resp.text}")

            files = resp.json().get("files", [])

            for f in files[:limite]:
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
                    nota_data = self._parsear_xml_nota(
                        xml_content, f["name"], f["id"]
                    )
                    if nota_data:
                        notas.append(nota_data)

                except Exception as e:
                    logger.warning(f"Erro ao processar {f['name']}: {e}")
                    continue

        return notas

    def _parsear_xml_nota(
        self,
        xml_content: bytes,
        filename: str,
        file_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Parseia XML com tratamento robusto de erros."""
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(xml_content)
            root_tag = root.tag.lower()

            if "nfeproc" in root_tag or "nfe" in root_tag:
                return self._parse_nfe_xml(root, filename, file_id)
            elif "nfse" in root_tag or "compnfse" in root_tag:
                return self._parse_nfse_xml(root, filename, file_id)
            elif "cteproc" in root_tag or "cte" in root_tag:
                return self._parse_cte_xml(root, filename, file_id)
            else:
                logger.warning(f"Tipo XML nao reconhecido: {root.tag}")
                return self._parse_generico(root, filename, file_id)

        except ET.ParseError as e:
            logger.error(f"XML malformado ({filename}): {e}")
            self._salvar_xml_erro(filename, xml_content, str(e))
            return None
        except Exception as e:
            logger.error(f"Erro ao parsear ({filename}): {e}")
            return None

    def _salvar_xml_erro(
        self, filename: str, xml_content: bytes, erro: str
    ):
        """Salva XMLs com erro para debug."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.makedirs("logs/xml_erros", exist_ok=True)
            erro_path = f"logs/xml_erros/{timestamp}_{filename}"

            with open(erro_path, "wb") as f:
                f.write(f"<!-- ERRO: {erro} -->\n".encode())
                f.write(xml_content)

            logger.info(f"XML salvo para debug: {erro_path}")
        except Exception:
            pass

    def _parse_generico(
        self, root, filename: str, file_id: str
    ) -> Dict[str, Any]:
        """Parser genérico para XMLs não reconhecidos."""
        return {
            "chave_acesso": None,
            "numero": self._safe_find(root, ".//Numero", "S/N"),
            "serie": self._safe_find(root, ".//Serie", "N/A"),
            "tipo": "Desconhecido",
            "data_emissao": None,
            "valor_total": 0.0,
            "cnpj_emitente": None,
            "nome_emitente": None,
            "cnpj_destinatario": None,
            "nome_destinatario": None,
            "situacao": "XML nao parseado",
            "arquivo_nome": filename,
            "drive_file_id": file_id,
        }

    def _safe_find(self, root, xpath: str, default: str = "") -> str:
        """Helper para buscar elementos com fallback."""
        elem = root.find(xpath)
        return elem.text if elem is not None and elem.text else default

    def _parse_nfe_xml(
        self, root, filename: str, file_id: str
    ) -> Dict[str, Any]:
        """Extrai dados de NF-e/NFC-e."""
        ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

        def find_text(xpath: str, default: str = "") -> str:
            elem = root.find(xpath, ns)
            if elem is None:
                # Tentar sem namespace
                xpath_no_ns = xpath.split("/")[-1].replace("nfe:", "")
                elem = root.find(f".//{xpath_no_ns}")
            return elem.text if elem is not None else default

        modelo = find_text(".//nfe:ide/nfe:mod", "55")
        tipo = "NFC-e" if modelo == "65" else "NF-e"

        return {
            "chave_acesso": find_text(".//nfe:infProt/nfe:chNFe"),
            "numero": find_text(".//nfe:ide/nfe:nNF"),
            "serie": find_text(".//nfe:ide/nfe:serie"),
            "tipo": tipo,
            "data_emissao": find_text(".//nfe:ide/nfe:dhEmi"),
            "valor_total": float(
                find_text(".//nfe:total/nfe:ICMSTot/nfe:vNF", "0") or "0"
            ),
            "cnpj_emitente": find_text(".//nfe:emit/nfe:CNPJ"),
            "nome_emitente": find_text(".//nfe:emit/nfe:xNome"),
            "cnpj_destinatario": find_text(".//nfe:dest/nfe:CNPJ"),
            "nome_destinatario": find_text(".//nfe:dest/nfe:xNome"),
            "situacao": (
                "autorizada"
                if find_text(".//nfe:infProt/nfe:cStat") == "100"
                else "pendente"
            ),
            "arquivo_nome": filename,
            "drive_file_id": file_id,
        }

    def _parse_nfse_xml(
        self, root, filename: str, file_id: str
    ) -> Dict[str, Any]:
        """Extrai dados de NFS-e."""

        def find_any(*xpaths: str) -> str:
            for xpath in xpaths:
                elem = root.find(f".//{xpath}")
                if elem is not None and elem.text:
                    return elem.text
            return ""

        valor_str = find_any(
            "ValorServicos", "valorServicos", "ValorTotal"
        ) or "0"
        try:
            valor = float(valor_str)
        except ValueError:
            valor = 0.0

        return {
            "chave_acesso": None,
            "numero": find_any("Numero", "NumeroNfse", "numero"),
            "serie": find_any("Serie", "serie"),
            "tipo": "NFS-e",
            "data_emissao": find_any("DataEmissao", "dataEmissao", "dhEmissao"),
            "valor_total": valor,
            "cnpj_emitente": find_any("Cnpj", "CnpjPrestador", "cnpjPrestador"),
            "nome_emitente": find_any(
                "RazaoSocial", "razaoSocial", "NomePrestador"
            ),
            "cnpj_destinatario": find_any("CnpjTomador", "cnpjTomador"),
            "nome_destinatario": find_any(
                "RazaoSocialTomador", "NomeTomador"
            ),
            "situacao": "autorizada",
            "arquivo_nome": filename,
            "drive_file_id": file_id,
        }

    def _parse_cte_xml(
        self, root, filename: str, file_id: str
    ) -> Dict[str, Any]:
        """Extrai dados de CT-e."""
        ns = {"cte": "http://www.portalfiscal.inf.br/cte"}

        def find_text(xpath: str, default: str = "") -> str:
            elem = root.find(xpath, ns)
            if elem is None:
                elem = root.find(f".//{xpath.split('/')[-1]}")
            return elem.text if elem is not None else default

        valor_str = find_text(".//cte:vPrest/cte:vTPrest", "0") or "0"
        try:
            valor = float(valor_str)
        except ValueError:
            valor = 0.0

        return {
            "chave_acesso": find_text(".//cte:infProt/cte:chCTe"),
            "numero": find_text(".//cte:ide/cte:nCT"),
            "serie": find_text(".//cte:ide/cte:serie"),
            "tipo": "CT-e",
            "data_emissao": find_text(".//cte:ide/cte:dhEmi"),
            "valor_total": valor,
            "cnpj_emitente": find_text(".//cte:emit/cte:CNPJ"),
            "nome_emitente": find_text(".//cte:emit/cte:xNome"),
            "cnpj_destinatario": find_text(".//cte:dest/cte:CNPJ"),
            "nome_destinatario": find_text(".//cte:dest/cte:xNome"),
            "situacao": "autorizada",
            "arquivo_nome": filename,
            "drive_file_id": file_id,
        }


# Singleton
google_drive_service = GoogleDriveService()

