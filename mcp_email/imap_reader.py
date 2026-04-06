"""
IMAP Email Reader

Módulo para leer y buscar correos en la bandeja de entrada mediante IMAP.
Soporta Gmail, Outlook, Yahoo y servidores IMAP personalizados.
"""

import imaplib
import asyncio
import email
import email.header
import email.utils
import socket
from email.policy import default as default_policy
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# Servidores IMAP predefinidos por proveedor (basados en smtp_config.server)
IMAP_PROVIDERS = {
    "smtp.gmail.com":        {"server": "imap.gmail.com",           "port": 993},
    "smtp-mail.outlook.com": {"server": "outlook.office365.com",    "port": 993},
    "smtp.office365.com":    {"server": "outlook.office365.com",    "port": 993},
    "smtp.mail.yahoo.com":   {"server": "imap.mail.yahoo.com",      "port": 993},
    "smtp.live.com":         {"server": "imap-mail.outlook.com",    "port": 993},
}


def _decode_header(value: str) -> str:
    """Decodifica encabezados de email con posibles encodings."""
    if not value:
        return ""
    parts = email.header.decode_header(value)
    decoded_parts = []
    for part, charset in parts:
        if isinstance(part, bytes):
            try:
                decoded_parts.append(part.decode(charset or "utf-8", errors="replace"))
            except Exception:
                decoded_parts.append(part.decode("utf-8", errors="replace"))
        else:
            decoded_parts.append(str(part))
    return " ".join(decoded_parts).strip()


def _extract_body(msg) -> str:
    """Extrae el cuerpo de texto del mensaje (prefiere text/plain, fallback text/html)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
                    break
            elif ct == "text/html" and "attachment" not in cd and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    # Limitar longitud para no sobrecargar el contexto del LLM
    return body[:2000] if len(body) > 2000 else body


def _parse_email_message(raw_data: bytes, email_id: str) -> dict:
    """Convierte bytes de un mensaje IMAP en un diccionario estructurado."""
    msg = email.message_from_bytes(raw_data)
    date_str = msg.get("Date", "")
    try:
        parsed_date = email.utils.parsedate_to_datetime(date_str)
        date_iso = parsed_date.isoformat()
    except Exception:
        date_iso = date_str

    return {
        "id": email_id,
        "from": _decode_header(msg.get("From", "")),
        "to": _decode_header(msg.get("To", "")),
        "subject": _decode_header(msg.get("Subject", "(Sin asunto)")),
        "date": date_iso,
        "body": _extract_body(msg),
        "has_attachments": any(
            part.get_content_disposition() == "attachment"
            for part in msg.walk()
        ),
    }


def _build_search_criteria(
    from_addr: Optional[str] = None,
    subject: Optional[str] = None,
    since_date: Optional[str] = None,
    keyword: Optional[str] = None,
    unseen_only: bool = False,
) -> str:
    """Construye el criterio de búsqueda IMAP a partir de los parámetros."""
    criteria_parts = []

    if unseen_only:
        criteria_parts.append("UNSEEN")
    if from_addr:
        criteria_parts.append(f'FROM "{from_addr}"')
    if subject:
        criteria_parts.append(f'SUBJECT "{subject}"')
    if since_date:
        # Acepta formatos: YYYY-MM-DD, DD-Mon-YYYY
        try:
            dt = datetime.strptime(since_date, "%Y-%m-%d")
            since_date = dt.strftime("%d-%b-%Y")
        except ValueError:
            pass  # Ya está en formato DD-Mon-YYYY
        criteria_parts.append(f'SINCE "{since_date}"')
    if keyword:
        criteria_parts.append(f'BODY "{keyword}"')

    return " ".join(criteria_parts) if criteria_parts else "ALL"


def _sync_read_inbox(
    imap_config: Dict[str, Any],
    limit: int = 10,
    folder: str = "INBOX",
) -> Dict[str, Any]:
    """Conecta vía IMAP y obtiene los últimos N emails de la carpeta."""
    server = imap_config.get("server")
    port = imap_config.get("port", 993)
    email_addr = imap_config.get("email")
    password = imap_config.get("password")

    if not all([server, email_addr, password]):
        return {"success": False, "error": "imap_config incompleto: se requiere server, email y password"}

    try:
        mail = imaplib.IMAP4_SSL(server, port, timeout=15)
        mail.login(email_addr, password)
        mail.select(folder, readonly=True)

        status, data = mail.search(None, "ALL")
        if status != "OK":
            mail.logout()
            return {"success": False, "error": "Error al buscar mensajes"}

        ids = data[0].split()
        # Tomar los últimos N (más recientes)
        ids = ids[-limit:] if len(ids) > limit else ids
        ids = list(reversed(ids))  # Más reciente primero

        emails = []
        for eid in ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status == "OK" and msg_data and msg_data[0]:
                raw = msg_data[0][1]
                if isinstance(raw, bytes):
                    parsed = _parse_email_message(raw, eid.decode())
                    emails.append(parsed)

        mail.logout()
        return {"success": True, "count": len(emails), "emails": emails, "folder": folder}

    except imaplib.IMAP4.error as e:
        return {"success": False, "error": f"Error IMAP: {str(e)}"}
    except socket.timeout:
        return {"success": False, "error": "Timeout al conectar con el servidor IMAP"}
    except OSError as e:
        return {"success": False, "error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error inesperado: {str(e)}"}


def _sync_search_emails(
    imap_config: Dict[str, Any],
    from_addr: Optional[str] = None,
    subject: Optional[str] = None,
    since_date: Optional[str] = None,
    keyword: Optional[str] = None,
    unseen_only: bool = False,
    limit: int = 10,
    folder: str = "INBOX",
) -> Dict[str, Any]:
    """Busca emails en la bandeja según criterios."""
    server = imap_config.get("server")
    port = imap_config.get("port", 993)
    email_addr = imap_config.get("email")
    password = imap_config.get("password")

    if not all([server, email_addr, password]):
        return {"success": False, "error": "imap_config incompleto: se requiere server, email y password"}

    try:
        criteria = _build_search_criteria(from_addr, subject, since_date, keyword, unseen_only)
        mail = imaplib.IMAP4_SSL(server, port, timeout=15)
        mail.login(email_addr, password)
        mail.select(folder, readonly=True)

        status, data = mail.search(None, criteria)
        if status != "OK":
            mail.logout()
            return {"success": False, "error": "Error en búsqueda IMAP"}

        ids = data[0].split()
        if not ids:
            mail.logout()
            return {"success": True, "count": 0, "emails": [], "criteria": criteria}

        # Más recientes primero
        ids = list(reversed(ids))
        ids = ids[:limit]

        emails = []
        for eid in ids:
            status, msg_data = mail.fetch(eid, "(RFC822)")
            if status == "OK" and msg_data and msg_data[0]:
                raw = msg_data[0][1]
                if isinstance(raw, bytes):
                    parsed = _parse_email_message(raw, eid.decode())
                    emails.append(parsed)

        mail.logout()
        return {"success": True, "count": len(emails), "emails": emails, "criteria": criteria}

    except imaplib.IMAP4.error as e:
        return {"success": False, "error": f"Error IMAP: {str(e)}"}
    except socket.timeout:
        return {"success": False, "error": "Timeout al conectar con el servidor IMAP"}
    except OSError as e:
        return {"success": False, "error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error inesperado: {str(e)}"}


def _sync_read_email(
    imap_config: Dict[str, Any],
    email_id: str,
    folder: str = "INBOX",
) -> Dict[str, Any]:
    """Obtiene el contenido completo de un email por su ID."""
    server = imap_config.get("server")
    port = imap_config.get("port", 993)
    email_addr = imap_config.get("email")
    password = imap_config.get("password")

    if not all([server, email_addr, password]):
        return {"success": False, "error": "imap_config incompleto: se requiere server, email y password"}

    try:
        mail = imaplib.IMAP4_SSL(server, port, timeout=15)
        mail.login(email_addr, password)
        mail.select(folder, readonly=True)

        status, msg_data = mail.fetch(email_id.encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            mail.logout()
            return {"success": False, "error": f"No se encontró el email con ID {email_id}"}

        raw = msg_data[0][1]
        if not isinstance(raw, bytes):
            mail.logout()
            return {"success": False, "error": "Datos del email inválidos"}

        parsed = _parse_email_message(raw, email_id)
        mail.logout()
        return {"success": True, "email": parsed}

    except imaplib.IMAP4.error as e:
        return {"success": False, "error": f"Error IMAP: {str(e)}"}
    except socket.timeout:
        return {"success": False, "error": "Timeout al conectar con el servidor IMAP"}
    except OSError as e:
        return {"success": False, "error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Error inesperado: {str(e)}"}


class IMAPReader:
    """Lector IMAP asíncrono para lectura y búsqueda de emails."""

    @staticmethod
    async def read_inbox(
        imap_config: Dict[str, Any],
        limit: int = 10,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """
        Obtiene los últimos N emails de la bandeja de entrada.

        Args:
            imap_config: {"server": str, "port": int, "email": str, "password": str}
            limit: Número máximo de emails a retornar (default: 10)
            folder: Carpeta IMAP (default: "INBOX")

        Returns:
            {"success": bool, "count": int, "emails": [...], "folder": str}
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _sync_read_inbox, imap_config, limit, folder
        )

    @staticmethod
    async def search_emails(
        imap_config: Dict[str, Any],
        from_addr: Optional[str] = None,
        subject: Optional[str] = None,
        since_date: Optional[str] = None,
        keyword: Optional[str] = None,
        unseen_only: bool = False,
        limit: int = 10,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """
        Busca emails según criterios.

        Args:
            imap_config: {"server": str, "port": int, "email": str, "password": str}
            from_addr: Filtrar por remitente (ej: "juan@example.com")
            subject: Filtrar por asunto (ej: "Factura")
            since_date: Desde fecha (ej: "2024-01-15" o "15-Jan-2024")
            keyword: Palabra clave en el cuerpo del email
            unseen_only: Solo emails no leídos
            limit: Número máximo de resultados (default: 10)
            folder: Carpeta IMAP (default: "INBOX")

        Returns:
            {"success": bool, "count": int, "emails": [...], "criteria": str}
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            _sync_search_emails,
            imap_config, from_addr, subject, since_date, keyword, unseen_only, limit, folder,
        )

    @staticmethod
    async def read_email(
        imap_config: Dict[str, Any],
        email_id: str,
        folder: str = "INBOX",
    ) -> Dict[str, Any]:
        """
        Obtiene el contenido completo de un email por su ID IMAP.

        Args:
            imap_config: {"server": str, "port": int, "email": str, "password": str}
            email_id: ID del email obtenido de read_inbox o search_emails
            folder: Carpeta donde está el email (default: "INBOX")

        Returns:
            {"success": bool, "email": {id, from, to, subject, date, body, has_attachments}}
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _sync_read_email, imap_config, email_id, folder
        )
