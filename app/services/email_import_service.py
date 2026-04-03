"""
Serviço de importação de notas fiscais via Email IMAP.

Suporta:
- Gmail (OAuth2 ou senha de app)
- Outlook (OAuth2 ou IMAP)
- Servidores IMAP genéricos

Fluxo:
1. Conectar ao servidor IMAP
2. Buscar emails com anexos XML
3. Extrair e parsear XMLs (NF-e, NFC-e, NFS-e, CT-e)
4. Deduplicar por chave_acesso
5. Salvar notas no banco
"""
import email
import imaplib
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO

from cryptography.fernet import Fernet
from lxml import etree

logger = logging.getLogger(__name__)


class EmailImportService:
    """Serviço singleton para importação de XMLs fiscais via IMAP."""

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
                logger.error(f"Erro ao inicializar Fernet para email: {e}")

    def _require_fernet(self, operation: str) -> Fernet:
        if not self._fernet:
            raise RuntimeError(
                "CERTIFICATE_ENCRYPTION_KEY inválida ou ausente. "
                f"Não foi possível {operation}."
            )
        return self._fernet

    # ============================================
    # CRIPTOGRAFIA DE CREDENCIAIS
    # ============================================

    def encrypt(self, value: str) -> str:
        fernet = self._require_fernet("criptografar credenciais de email")
        return fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        fernet = self._require_fernet("descriptografar credenciais de email")
        try:
            return fernet.decrypt(value.encode()).decode()
        except Exception:
            return value

    # ============================================
    # GERENCIAMENTO DE CONFIGURAÇÕES
    # ============================================

    async def salvar_configuracao(
        self,
        user_id: str,
        dados: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Salva ou atualiza configuração de email."""
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()

        record = {
            "user_id": user_id,
            "tipo": dados.get("tipo", "escritorio"),
            "provedor": dados.get("provedor", "imap_generico"),
            "email": dados["email"],
            "ativo": True,
        }

        if dados.get("empresa_id"):
            record["empresa_id"] = dados["empresa_id"]

        # IMAP genérico
        if dados.get("imap_host"):
            record["imap_host"] = dados["imap_host"]
            record["imap_port"] = dados.get("imap_port", 993)
            record["imap_usuario"] = dados.get("imap_usuario", dados["email"])
            if dados.get("imap_senha"):
                record["imap_senha_encrypted"] = self.encrypt(dados["imap_senha"])

        # OAuth tokens
        if dados.get("oauth_access_token"):
            record["oauth_access_token_encrypted"] = self.encrypt(
                dados["oauth_access_token"]
            )
        if dados.get("oauth_refresh_token"):
            record["oauth_refresh_token_encrypted"] = self.encrypt(
                dados["oauth_refresh_token"]
            )
        if dados.get("oauth_token_expiry"):
            record["oauth_token_expiry"] = dados["oauth_token_expiry"]

        if dados.get("pastas_monitoradas"):
            record["pastas_monitoradas"] = dados["pastas_monitoradas"]

        # Upsert
        if dados.get("id"):
            result = (
                db.table("configuracoes_email")
                .update(record)
                .eq("id", dados["id"])
                .eq("user_id", user_id)
                .execute()
            )
        else:
            result = db.table("configuracoes_email").insert(record).execute()

        if result.data:
            return result.data[0]
        raise Exception("Erro ao salvar configuração de email")

    async def listar_configuracoes(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        """Lista configurações de email do usuário (sem dados sensíveis)."""
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        result = (
            db.table("configuracoes_email")
            .select("id, user_id, empresa_id, tipo, provedor, email, "
                    "imap_host, imap_port, pastas_monitoradas, "
                    "ultima_sincronizacao, total_importadas, ativo, "
                    "created_at, updated_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data or []

    async def remover_configuracao(self, config_id: str, user_id: str) -> bool:
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()
        result = (
            db.table("configuracoes_email")
            .delete()
            .eq("id", config_id)
            .eq("user_id", user_id)
            .execute()
        )
        return bool(result.data)

    # ============================================
    # CONEXÃO IMAP
    # ============================================

    def _conectar_imap(self, config: Dict[str, Any]) -> imaplib.IMAP4_SSL:
        """Cria conexão IMAP com base na configuração."""
        provedor = config.get("provedor", "imap_generico")

        if provedor == "gmail":
            host = "imap.gmail.com"
            port = 993
        elif provedor == "outlook":
            host = "outlook.office365.com"
            port = 993
        else:
            host = config.get("imap_host", "")
            port = config.get("imap_port", 993)

        if not host:
            raise ValueError("Host IMAP não configurado")

        logger.info(f"Conectando IMAP: {host}:{port}")
        conn = imaplib.IMAP4_SSL(host, port)

        # Autenticação
        usuario = config.get("imap_usuario") or config.get("email", "")
        senha_enc = config.get("imap_senha_encrypted", "")
        if senha_enc:
            senha = self.decrypt(senha_enc)
        else:
            raise ValueError("Senha IMAP não configurada")

        conn.login(usuario, senha)
        logger.info(f"IMAP login OK: {usuario}")
        return conn

    # ============================================
    # BUSCA E EXTRAÇÃO DE XMLS
    # ============================================

    def _buscar_emails_com_xml(
        self,
        conn: imaplib.IMAP4_SSL,
        pasta: str = "INBOX",
        desde: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Busca emails com anexos XML na pasta especificada."""
        conn.select(pasta, readonly=True)

        # Critério de busca
        criterio = "ALL"
        if desde:
            data_str = desde.strftime("%d-%b-%Y")
            criterio = f'(SINCE {data_str})'

        status_code, msg_ids = conn.search(None, criterio)
        if status_code != "OK":
            return []

        ids = msg_ids[0].split()
        logger.info(f"Encontrados {len(ids)} emails em {pasta}")

        resultados = []

        for msg_id in ids[-500:]:  # Limitar a 500 emails por vez
            try:
                _, msg_data = conn.fetch(msg_id, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                xmls = self._extrair_xmls_do_email(msg)
                if xmls:
                    assunto = self._decode_header(msg.get("Subject", ""))
                    remetente = self._decode_header(msg.get("From", ""))
                    data = msg.get("Date", "")

                    resultados.append({
                        "msg_id": msg_id.decode(),
                        "assunto": assunto,
                        "remetente": remetente,
                        "data": data,
                        "xmls": xmls,
                    })
            except Exception as e:
                logger.error(f"Erro ao processar email {msg_id}: {e}")
                continue

        logger.info(f"Emails com XML encontrados: {len(resultados)}")
        return resultados

    def _extrair_xmls_do_email(
        self, msg: email.message.Message
    ) -> List[Dict[str, Any]]:
        """Extrai arquivos XML de um email (anexos)."""
        xmls = []

        if not msg.is_multipart():
            return xmls

        for part in msg.walk():
            content_type = part.get_content_type()
            filename = part.get_filename()

            if filename:
                filename = self._decode_header(filename)

            # Verificar se é XML pelo tipo ou extensão
            is_xml = (
                content_type in ("text/xml", "application/xml",
                                 "application/octet-stream")
                and filename
                and filename.lower().endswith(".xml")
            )

            if not is_xml and filename and filename.lower().endswith(".xml"):
                is_xml = True

            if is_xml:
                payload = part.get_payload(decode=True)
                if payload:
                    xmls.append({
                        "filename": filename,
                        "content": payload,
                        "size": len(payload),
                    })

        return xmls

    def _decode_header(self, value: str) -> str:
        """Decodifica header de email."""
        if not value:
            return ""
        parts = decode_header(value)
        decoded = []
        for part, charset in parts:
            if isinstance(part, bytes):
                decoded.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(str(part))
        return " ".join(decoded)

    # ============================================
    # PROCESSAMENTO E IMPORTAÇÃO
    # ============================================

    async def sincronizar(
        self,
        config_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Sincroniza emails e importa XMLs fiscais.

        Returns:
            Resumo da sincronização
        """
        from app.db.supabase_client import get_supabase_admin

        db = get_supabase_admin()

        # Buscar configuração
        result = (
            db.table("configuracoes_email")
            .select("*")
            .eq("id", config_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if not result.data:
            raise ValueError("Configuração de email não encontrada")

        config = result.data
        if not config.get("ativo"):
            raise ValueError("Configuração de email desativada")

        # Definir data de busca
        desde = None
        if config.get("ultima_sincronizacao"):
            desde = datetime.fromisoformat(
                config["ultima_sincronizacao"].replace("Z", "+00:00")
            )
        else:
            desde = datetime.now(timezone.utc) - timedelta(days=90)

        # Conectar e buscar
        conn = None
        resumo = {
            "config_id": config_id,
            "emails_processados": 0,
            "xmls_encontrados": 0,
            "notas_importadas": 0,
            "notas_duplicadas": 0,
            "erros": 0,
            "detalhes_erros": [],
        }

        try:
            conn = self._conectar_imap(config)
            pastas = config.get("pastas_monitoradas") or ["INBOX"]

            for pasta in pastas:
                emails = self._buscar_emails_com_xml(conn, pasta, desde)
                resumo["emails_processados"] += len(emails)

                for email_data in emails:
                    for xml_data in email_data["xmls"]:
                        resumo["xmls_encontrados"] += 1
                        try:
                            resultado = await self._processar_xml(
                                xml_content=xml_data["content"],
                                filename=xml_data["filename"],
                                user_id=user_id,
                                empresa_id=config.get("empresa_id"),
                                config_id=config_id,
                                fonte="email",
                            )
                            if resultado == "importada":
                                resumo["notas_importadas"] += 1
                            elif resultado == "duplicada":
                                resumo["notas_duplicadas"] += 1
                        except Exception as e:
                            resumo["erros"] += 1
                            resumo["detalhes_erros"].append(
                                f"{xml_data['filename']}: {str(e)}"
                            )

        except Exception as e:
            logger.error(f"Erro na sincronização IMAP: {e}")
            resumo["erro_geral"] = str(e)
        finally:
            if conn:
                try:
                    conn.logout()
                except Exception:
                    pass

        # Atualizar última sincronização
        db.table("configuracoes_email").update({
            "ultima_sincronizacao": datetime.now(timezone.utc).isoformat(),
            "total_importadas": (config.get("total_importadas", 0)
                                 + resumo["notas_importadas"]),
        }).eq("id", config_id).execute()

        logger.info(
            f"Sincronização email concluída: "
            f"{resumo['notas_importadas']} importadas, "
            f"{resumo['notas_duplicadas']} duplicadas, "
            f"{resumo['erros']} erros"
        )

        return resumo

    async def _processar_xml(
        self,
        xml_content: bytes,
        filename: str,
        user_id: str,
        empresa_id: Optional[str],
        config_id: str,
        fonte: str,
    ) -> str:
        """
        Processa um XML fiscal e salva no banco.

        Returns:
            'importada', 'duplicada', ou 'erro'
        """
        from app.db.supabase_client import get_supabase_admin
        from app.services.real_consulta_service import real_consulta_service

        db = get_supabase_admin()

        try:
            # Detectar tipo e parsear
            root = etree.fromstring(xml_content)
            tipo_doc = self._detectar_tipo_documento(root)

            if tipo_doc == "desconhecido":
                await self._registrar_log(
                    db, user_id, empresa_id, fonte, config_id,
                    filename, tipo_doc, None, None, "ignorada",
                    "XML não é documento fiscal reconhecido"
                )
                return "ignorada"

            # Determinar empresa_id se modo escritório
            target_empresa_id = empresa_id
            if not target_empresa_id:
                # Tentar associar pelo CNPJ do destinatário
                cnpj = self._extrair_cnpj_destinatario(root, tipo_doc)
                if cnpj:
                    target_empresa_id = await self._buscar_empresa_por_cnpj(
                        db, user_id, cnpj
                    )

            if not target_empresa_id:
                # Tentar pelo CNPJ do emitente
                cnpj_emit = self._extrair_cnpj_emitente(root, tipo_doc)
                if cnpj_emit:
                    target_empresa_id = await self._buscar_empresa_por_cnpj(
                        db, user_id, cnpj_emit
                    )

            if not target_empresa_id:
                await self._registrar_log(
                    db, user_id, None, fonte, config_id,
                    filename, tipo_doc, None, None, "ignorada",
                    "Não foi possível associar a uma empresa cadastrada"
                )
                return "ignorada"

            # Parsear usando real_consulta_service
            if tipo_doc in ("nfe", "nfce"):
                nota_create, metadados = real_consulta_service.importar_xml(
                    xml_content, target_empresa_id
                )
            elif tipo_doc == "nfse":
                # NFS-e via XML é raro mas possível
                nota_create, metadados = self._parse_nfse_xml(
                    root, target_empresa_id
                )
            elif tipo_doc == "cte":
                nota_create, metadados = self._parse_cte_xml_basico(
                    root, target_empresa_id
                )
            else:
                return "ignorada"

            chave = nota_create.chave_acesso

            # Verificar duplicata
            if chave:
                existing = (
                    db.table("notas_fiscais")
                    .select("id")
                    .eq("chave_acesso", chave)
                    .eq("empresa_id", target_empresa_id)
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    await self._registrar_log(
                        db, user_id, target_empresa_id, fonte, config_id,
                        filename, tipo_doc, chave, existing.data[0]["id"],
                        "duplicada", "Nota já existe no banco"
                    )
                    return "duplicada"

            # Inserir nota
            nota_dict = nota_create.model_dump(exclude_none=True)
            # Converter Decimal para float para JSON
            for k, v in nota_dict.items():
                if hasattr(v, "as_tuple"):  # Decimal
                    nota_dict[k] = float(v)
                elif isinstance(v, datetime):
                    nota_dict[k] = v.isoformat()

            nota_dict["fonte"] = fonte
            if metadados.get("xml_completo"):
                nota_dict["xml_completo"] = metadados["xml_completo"]

            insert_result = db.table("notas_fiscais").insert(nota_dict).execute()

            nota_id = None
            if insert_result.data:
                nota_id = insert_result.data[0].get("id")

            await self._registrar_log(
                db, user_id, target_empresa_id, fonte, config_id,
                filename, tipo_doc, chave, nota_id, "sucesso",
                f"Nota importada: {nota_create.nome_emitente}"
            )

            return "importada"

        except Exception as e:
            logger.error(f"Erro ao processar XML {filename}: {e}")
            await self._registrar_log(
                db, user_id, empresa_id, fonte, config_id,
                filename, "desconhecido", None, None, "erro", str(e)
            )
            raise

    # ============================================
    # HELPERS DE XML
    # ============================================

    def _detectar_tipo_documento(self, root) -> str:
        """Detecta tipo de documento fiscal pelo XML."""
        tag = etree.QName(root).localname.lower() if isinstance(root.tag, str) else ""
        full_tag = root.tag.lower() if isinstance(root.tag, str) else ""

        if "nfse" in full_tag:
            return "nfse"
        if "nfe" in full_tag or "nfeproc" in full_tag:
            # Verificar modelo para distinguir NF-e de NFC-e
            ns = {"nfe": "http://www.portalfiscal.inf.br/nfe"}
            mod = root.find(".//{http://www.portalfiscal.inf.br/nfe}mod")
            if mod is not None and mod.text == "65":
                return "nfce"
            return "nfe"
        if "cte" in full_tag or "cteproc" in full_tag:
            return "cte"

        # Verificar filhos
        for child in root:
            child_tag = child.tag.lower() if isinstance(child.tag, str) else ""
            if "infnfe" in child_tag:
                return "nfe"
            if "infcte" in child_tag:
                return "cte"

        return "desconhecido"

    def _extrair_cnpj_destinatario(self, root, tipo_doc: str) -> Optional[str]:
        """Extrai CNPJ do destinatário do XML."""
        ns = "http://www.portalfiscal.inf.br/nfe"
        if tipo_doc in ("nfe", "nfce"):
            elem = root.find(f".//{{{ns}}}dest/{{{ns}}}CNPJ")
            if elem is not None and elem.text:
                return re.sub(r"\D", "", elem.text)
        return None

    def _extrair_cnpj_emitente(self, root, tipo_doc: str) -> Optional[str]:
        """Extrai CNPJ do emitente do XML."""
        ns = "http://www.portalfiscal.inf.br/nfe"
        if tipo_doc in ("nfe", "nfce"):
            elem = root.find(f".//{{{ns}}}emit/{{{ns}}}CNPJ")
            if elem is not None and elem.text:
                return re.sub(r"\D", "", elem.text)
        return None

    async def _buscar_empresa_por_cnpj(
        self, db, user_id: str, cnpj: str
    ) -> Optional[str]:
        """Busca empresa pelo CNPJ (formatado ou não)."""
        # Formatar CNPJ
        cnpj_limpo = re.sub(r"\D", "", cnpj)
        if len(cnpj_limpo) != 14:
            return None

        cnpj_fmt = (
            f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}"
            f"/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
        )

        result = (
            db.table("empresas")
            .select("id")
            .eq("usuario_id", user_id)
            .eq("cnpj", cnpj_fmt)
            .limit(1)
            .execute()
        )

        if result.data:
            return result.data[0]["id"]
        return None

    def _parse_nfse_xml(self, root, empresa_id: str):
        """Parse básico de XML NFS-e (variados formatos)."""
        from app.models.nota_fiscal import NotaFiscalCreate

        # Tentar extrair dados comuns de NFS-e
        numero = self._find_text(root, "Numero") or self._find_text(root, "NumeroNfse") or "0"
        valor = self._find_text(root, "ValorServicos") or self._find_text(root, "ValorTotal") or "0"
        cnpj_prest = self._find_text(root, "CnpjPrestador") or self._find_text(root, "Cnpj") or ""
        nome_prest = self._find_text(root, "RazaoSocialPrestador") or self._find_text(root, "RazaoSocial") or ""
        data_str = self._find_text(root, "DataEmissao") or ""

        data_emissao = datetime.now()
        if data_str:
            try:
                data_emissao = datetime.fromisoformat(data_str.replace("Z", "+00:00"))
            except Exception:
                pass

        nota = NotaFiscalCreate(
            empresa_id=empresa_id,
            numero_nf=numero,
            serie="U",
            tipo_nf="NFSe",
            data_emissao=data_emissao,
            valor_total=float(valor),
            cnpj_emitente=cnpj_prest if len(re.sub(r"\D", "", cnpj_prest)) == 14 else "00000000000000",
            nome_emitente=nome_prest,
            situacao="autorizada",
            fonte="email",
        )
        metadados = {"xml_completo": etree.tostring(root, encoding="unicode")}
        return nota, metadados

    def _parse_cte_xml_basico(self, root, empresa_id: str):
        """Parse básico de XML CT-e."""
        from app.models.nota_fiscal import NotaFiscalCreate

        ns_cte = "http://www.portalfiscal.inf.br/cte"

        inf_cte = root.find(f".//{{{ns_cte}}}infCte")
        chave_raw = inf_cte.get("Id", "") if inf_cte is not None else ""
        chave = chave_raw.replace("CTe", "") if chave_raw else None

        ide = root.find(f".//{{{ns_cte}}}ide")
        numero = self._find_text_ns(ide, "nCT", ns_cte) or "0"
        serie = self._find_text_ns(ide, "serie", ns_cte) or "1"
        data_str = self._find_text_ns(ide, "dhEmi", ns_cte) or ""

        emit = root.find(f".//{{{ns_cte}}}emit")
        cnpj_emit = self._find_text_ns(emit, "CNPJ", ns_cte) or ""
        nome_emit = self._find_text_ns(emit, "xNome", ns_cte) or ""

        vprest = root.find(f".//{{{ns_cte}}}vPrest")
        valor = self._find_text_ns(vprest, "vTPrest", ns_cte) or "0"

        prot = root.find(f".//{{{ns_cte}}}protCTe")
        protocolo = ""
        if prot is not None:
            protocolo = self._find_text_ns(prot.find(f".//{{{ns_cte}}}infProt"), "nProt", ns_cte) or ""

        data_emissao = datetime.now()
        if data_str:
            data_str_clean = re.sub(r"[+-]\d{2}:\d{2}$", "", data_str)
            try:
                data_emissao = datetime.fromisoformat(data_str_clean)
            except Exception:
                pass

        nota = NotaFiscalCreate(
            empresa_id=empresa_id,
            chave_acesso=chave if chave and len(chave) == 44 else None,
            numero_nf=numero,
            serie=serie,
            tipo_nf="CTe",
            modelo="57",
            data_emissao=data_emissao,
            valor_total=float(valor),
            cnpj_emitente=cnpj_emit if len(re.sub(r"\D", "", cnpj_emit)) == 14 else "00000000000000",
            nome_emitente=nome_emit,
            situacao="autorizada",
            protocolo=protocolo,
            fonte="email",
        )
        metadados = {"xml_completo": etree.tostring(root, encoding="unicode")}
        return nota, metadados

    def _find_text(self, root, tag: str) -> Optional[str]:
        """Busca texto em qualquer namespace."""
        # Com qualquer namespace
        for elem in root.iter():
            local = etree.QName(elem).localname if isinstance(elem.tag, str) else ""
            if local == tag and elem.text:
                return elem.text.strip()
        return None

    def _find_text_ns(self, parent, tag: str, ns: str) -> Optional[str]:
        """Busca texto com namespace específico."""
        if parent is None:
            return None
        elem = parent.find(f".//{{{ns}}}{tag}")
        if elem is not None and elem.text:
            return elem.text.strip()
        # Sem namespace
        elem = parent.find(f".//{tag}")
        if elem is not None and elem.text:
            return elem.text.strip()
        return None

    async def _registrar_log(
        self, db, user_id, empresa_id, fonte, config_id,
        arquivo_nome, tipo_documento, chave_acesso, nota_fiscal_id,
        status, mensagem
    ):
        """Registra log de importação."""
        try:
            record = {
                "user_id": user_id,
                "fonte": fonte,
                "config_id": config_id,
                "arquivo_nome": arquivo_nome,
                "tipo_documento": tipo_documento,
                "status": status,
                "mensagem": mensagem,
            }
            if empresa_id:
                record["empresa_id"] = empresa_id
            if chave_acesso:
                record["chave_acesso"] = chave_acesso
            if nota_fiscal_id:
                record["nota_fiscal_id"] = nota_fiscal_id

            db.table("log_importacao").insert(record).execute()
        except Exception as e:
            logger.error(f"Erro ao registrar log de importação: {e}")


# Singleton
email_import_service = EmailImportService()
