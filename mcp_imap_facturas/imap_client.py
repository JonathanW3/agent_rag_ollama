"""
Cliente IMAP con conexión persistente y lazy connect.

Lee credenciales desde variables de entorno; NUNCA las recibe como parámetros.
Usa imap-tools para una API más ergonómica que imaplib directo.
"""

import logging
import os
import re
import sys
import threading
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from imap_tools import AND, MailBox, MailMessage

load_dotenv()

logger = logging.getLogger(__name__)

# ── Configuración desde entorno ───────────────────────────────────────────────
IMAP_SERVER   = os.getenv("IMAP_SERVER", "mail.webpossa.com")
IMAP_PORT     = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER     = os.getenv("IMAP_USER", "")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD", "")
IMAP_USE_SSL  = os.getenv("IMAP_USE_SSL", "true").lower() == "true"

# ── Conexión persistente ──────────────────────────────────────────────────────
_conn_lock = threading.Lock()
_mailbox: Optional[MailBox] = None

TAG = "[IMAP_FACTURAS]"


def _log(msg: str) -> None:
    """Imprime a stderr con prefijo para no contaminar stdout del protocolo MCP."""
    print(f"{TAG} {msg}", file=sys.stderr, flush=True)


def _connect() -> MailBox:
    """Abre una conexión IMAP nueva. Lanza ValueError si faltan credenciales."""
    if not IMAP_USER or not IMAP_PASSWORD:
        raise ValueError(
            "IMAP_USER e IMAP_PASSWORD son requeridas. "
            "Configura las variables de entorno en .env."
        )
    _log(f"Conectando a {IMAP_SERVER}:{IMAP_PORT} como {IMAP_USER} ...")
    mb = MailBox(IMAP_SERVER, IMAP_PORT)
    mb.login(IMAP_USER, IMAP_PASSWORD)
    _log(f"Conexión establecida OK → {IMAP_SERVER}:{IMAP_PORT}")
    return mb


def get_connection() -> MailBox:
    """
    Devuelve la conexión IMAP activa, reconectando si es necesario.
    Thread-safe mediante _conn_lock.
    """
    global _mailbox
    with _conn_lock:
        if _mailbox is not None:
            try:
                _mailbox.client.noop()
                _log("Reutilizando conexión activa (NOOP OK)")
                return _mailbox
            except Exception as exc:
                _log(f"Conexión caída ({exc}), reconectando...")
                try:
                    _mailbox.logout()
                except Exception:
                    pass
                _mailbox = None

        _mailbox = _connect()
        return _mailbox


def _mailbox_error_hint(folder: str, exc: Exception) -> str:
    """Devuelve un mensaje de error enriquecido con sugerencia de acción."""
    msg = str(exc)
    if "no such mailbox" in msg.lower() or "doesn't exist" in msg.lower():
        return (
            f"La carpeta '{folder}' no existe en el servidor. "
            f"Error original: {msg} — "
            "Usa la herramienta list_folders para ver las carpetas disponibles "
            "y encontrar el nombre correcto de tu carpeta Enviados."
        )
    return msg


# ── Helpers de parseo ─────────────────────────────────────────────────────────

def _parse_date(date_str: str) -> date:
    return datetime.strptime(date_str, "%Y-%m-%d").date()


def _normalize_email(addr: str) -> str:
    return addr.strip().lower()


def _msg_to_meta(msg: MailMessage) -> Dict[str, Any]:
    return {
        "uid": msg.uid,
        "date": msg.date.isoformat() if msg.date else None,
        "from": msg.from_,
        "to": list(msg.to),
        "subject": msg.subject,
        "has_attachments": len(msg.attachments) > 0,
        "attachment_names": [a.filename for a in msg.attachments],
    }


def _build_criteria(**kwargs: Any):
    return AND(**kwargs) if kwargs else AND(all=True)


# ── Operaciones IMAP síncronas ────────────────────────────────────────────────

def list_folders() -> Dict[str, Any]:
    """Lista todas las carpetas del buzón."""
    _log("list_folders → consultando carpetas del buzón...")
    try:
        mb = get_connection()
        folders = list(mb.folder.list())
        names = [f.name for f in folders]
        _log(f"list_folders → {len(folders)} carpeta(s): {', '.join(names)}")
        return {
            "success": True,
            "count": len(folders),
            "folders": [
                {
                    "name": f.name,
                    "delimiter": getattr(f, "delimiter", None),
                    "flags": list(getattr(f, "flags", [])),
                }
                for f in folders
            ],
        }
    except Exception as exc:
        _log(f"list_folders ERROR: {exc}")
        return {"success": False, "error": str(exc)}


def search_emails(
    folder: str = "INBOX",
    since_date: Optional[str] = None,
    before_date: Optional[str] = None,
    from_address: Optional[str] = None,
    to_address: Optional[str] = None,
    subject_contains: Optional[str] = None,
    has_attachments: Optional[bool] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Busca emails con filtros y devuelve solo metadata (sin cuerpo)."""
    criteria_desc = " | ".join(filter(None, [
        f"desde={since_date}" if since_date else None,
        f"hasta={before_date}" if before_date else None,
        f"de={from_address}" if from_address else None,
        f"para={to_address}" if to_address else None,
        f"asunto={subject_contains!r}" if subject_contains else None,
        f"adjuntos={has_attachments}" if has_attachments is not None else None,
        f"límite={limit}",
    ]))
    _log(f"search_emails folder={folder!r} [{criteria_desc}]")
    try:
        mb = get_connection()
        mb.folder.set(folder)
        _log(f"search_emails → carpeta '{folder}' seleccionada OK")

        criteria_kwargs: Dict[str, Any] = {}
        if since_date:
            criteria_kwargs["date_gte"] = _parse_date(since_date)
        if before_date:
            criteria_kwargs["date_lt"] = _parse_date(before_date)
        if from_address:
            criteria_kwargs["from_"] = from_address
        if to_address:
            criteria_kwargs["to"] = to_address
        if subject_contains:
            criteria_kwargs["subject"] = subject_contains

        criteria = _build_criteria(**criteria_kwargs)
        _log(f"search_emails → criterio IMAP: {criteria}")

        safe_limit = limit if (limit and limit > 0) else None
        results: List[Dict[str, Any]] = []
        for msg in mb.fetch(criteria, mark_seen=False, reverse=True, limit=safe_limit):
            meta = _msg_to_meta(msg)
            if has_attachments is not None and meta["has_attachments"] != has_attachments:
                continue
            results.append(meta)

        _log(f"search_emails → {len(results)} email(s) encontrado(s) en '{folder}'")
        if results:
            _log(f"search_emails → primer resultado: uid={results[0]['uid']} fecha={results[0]['date']} asunto={results[0]['subject']!r}")

        diagnostic: Optional[Dict] = None
        if len(results) == 0 and subject_contains:
            _log(f"search_emails → 0 resultados con asunto={subject_contains!r}. Buscando sin filtro para diagnóstico...")
            diag_kwargs = {k: v for k, v in criteria_kwargs.items() if k != "subject"}
            diag_criteria = _build_criteria(**diag_kwargs)
            sample_subjects: List[str] = []
            period_count = 0
            for msg in mb.fetch(diag_criteria, mark_seen=False, reverse=True, limit=20):
                period_count += 1
                subj = (msg.subject or "").strip()
                if subj and subj not in sample_subjects:
                    sample_subjects.append(subj)
                if len(sample_subjects) >= 10:
                    break
            _log(f"search_emails → sin filtro en período: {period_count} email(s), asuntos: {sample_subjects}")

            # Si el período también tiene 0 emails, buscar los últimos 2 meses sin filtro de asunto
            recent_emails: List[Dict] = []
            if period_count == 0:
                from datetime import timedelta as _td
                two_months_ago = (date.today().replace(day=1) - _td(days=1)).replace(day=1) - _td(days=1)
                two_months_ago = two_months_ago.replace(day=1)
                _log(f"search_emails → 0 emails en el período. Buscando desde {two_months_ago} sin filtro de asunto...")
                recent_criteria = AND(date_gte=two_months_ago)
                for msg in mb.fetch(recent_criteria, mark_seen=False, reverse=True, limit=100):
                    recent_emails.append({
                        "date": msg.date.isoformat()[:10] if msg.date else "?",
                        "subject": (msg.subject or "")[:60],
                        "from": (msg.from_ or "")[:50],
                    })
                _log(f"search_emails → emails últimos 2 meses: {len(recent_emails)}")

            hint = f"0 emails encontrados con asunto que contenga {subject_contains!r}. "
            if period_count == 0 and recent_emails:
                hint += (
                    f"La carpeta '{folder}' no tiene emails en el período indicado. "
                    f"Se encontraron {len(recent_emails)} email(s) en los últimos 2 meses."
                )
            elif period_count == 0:
                hint += f"La carpeta '{folder}' está vacía o no tiene emails en los últimos 2 meses."
            else:
                hint += f"Asuntos reales en el período: {sample_subjects if sample_subjects else '(ninguno)'}"

            diagnostic = {
                "hint": hint,
                "sample_subjects": sample_subjects,
                **({"recent_emails": recent_emails} if recent_emails else {}),
            }

        return {
            "success": True,
            "folder": folder,
            "since_date": since_date,
            "before_date": before_date,
            "subject_contains": subject_contains,
            "count": len(results),
            "emails": results,
            **({"diagnostic": diagnostic} if diagnostic else {}),
        }
    except Exception as exc:
        error_msg = _mailbox_error_hint(folder, exc)
        _log(f"search_emails ERROR en '{folder}': {error_msg}")
        return {"success": False, "error": error_msg}


def get_email_detail(uid: str, folder: str = "INBOX") -> Dict[str, Any]:
    """Devuelve el email completo (cuerpo en texto plano + metadata de adjuntos)."""
    _log(f"get_email_detail uid={uid!r} folder={folder!r}")
    try:
        mb = get_connection()
        mb.folder.set(folder)

        msgs = list(mb.fetch(AND(uid=[uid]), mark_seen=False))
        if not msgs:
            _log(f"get_email_detail → UID {uid!r} no encontrado en '{folder}'")
            return {"success": False, "error": f"Email con UID {uid!r} no encontrado en carpeta {folder!r}"}

        msg = msgs[0]
        att_count = len(msg.attachments)
        _log(
            f"get_email_detail → OK uid={msg.uid} "
            f"fecha={msg.date} asunto={msg.subject!r} adjuntos={att_count}"
        )
        return {
            "success": True,
            "email": {
                "uid": msg.uid,
                "date": msg.date.isoformat() if msg.date else None,
                "from": msg.from_,
                "to": list(msg.to),
                "subject": msg.subject,
                "body_text": (msg.text or "")[:5000],
                "has_attachments": att_count > 0,
                "attachments": [
                    {"filename": a.filename, "size_bytes": len(a.payload), "content_type": a.content_type}
                    for a in msg.attachments
                ],
            },
        }
    except Exception as exc:
        error_msg = _mailbox_error_hint(folder, exc)
        _log(f"get_email_detail ERROR uid={uid!r}: {error_msg}")
        return {"success": False, "error": error_msg}


def _collect_recipients(
    folder: str,
    since_date: str,
    before_date: str,
    subject_contains: Optional[str],
) -> Tuple[bool, Any]:
    """
    Recolecta {email_normalizado: {count, last_date}} para el período dado.
    Devuelve (True, dict) o (False, mensaje_error).
    """
    subject_info = f" asunto={subject_contains!r}" if subject_contains else ""
    _log(f"_collect_recipients folder={folder!r} {since_date}→{before_date}{subject_info}")
    try:
        mb = get_connection()
        mb.folder.set(folder)
        _log(f"_collect_recipients → carpeta '{folder}' seleccionada OK")

        criteria_kwargs: Dict[str, Any] = {
            "date_gte": _parse_date(since_date),
            "date_lt": _parse_date(before_date),
        }
        if subject_contains:
            criteria_kwargs["subject"] = subject_contains

        criteria = _build_criteria(**criteria_kwargs)
        _log(f"_collect_recipients → criterio IMAP: {criteria}")

        recipients: Dict[str, Dict[str, Any]] = {}
        msg_count = 0
        for msg in mb.fetch(criteria, mark_seen=False, headers_only=True):
            msg_count += 1
            msg_date_iso = msg.date.isoformat() if msg.date else None
            for addr in msg.to:
                norm = _normalize_email(addr)
                if not norm:
                    continue
                if norm not in recipients:
                    recipients[norm] = {"count": 0, "last_date": None}
                recipients[norm]["count"] += 1
                if msg_date_iso and (
                    recipients[norm]["last_date"] is None
                    or msg_date_iso > recipients[norm]["last_date"]
                ):
                    recipients[norm]["last_date"] = msg_date_iso

        _log(
            f"_collect_recipients → {msg_count} mensaje(s) leído(s), "
            f"{len(recipients)} destinatario(s) único(s)"
        )
        if recipients:
            sample = list(recipients.keys())[:3]
            _log(f"_collect_recipients → muestra destinatarios: {sample}")

        # Diagnóstico: si 0 resultados con filtro de asunto, buscar sin filtro
        # para mostrar qué asuntos existen realmente en el período.
        sample_subjects: List[str] = []
        total_without_filter: int = 0
        if msg_count == 0 and subject_contains:
            _log(
                f"_collect_recipients → 0 resultados con asunto={subject_contains!r}. "
                "Buscando sin filtro de asunto para diagnóstico..."
            )
            fallback_kwargs = {
                "date_gte": _parse_date(since_date),
                "date_lt": _parse_date(before_date),
            }
            for msg in mb.fetch(_build_criteria(**fallback_kwargs), mark_seen=False, headers_only=True, limit=20):
                total_without_filter += 1
                if msg.subject and len(sample_subjects) < 10:
                    sample_subjects.append(msg.subject)
            _log(
                f"_collect_recipients → sin filtro: {total_without_filter} mensaje(s) en el período. "
                f"Asuntos encontrados: {sample_subjects}"
            )

        return True, recipients, {"sample_subjects": sample_subjects, "total_without_filter": total_without_filter}
    except Exception as exc:
        error_msg = _mailbox_error_hint(folder, exc)
        _log(f"_collect_recipients ERROR en '{folder}': {error_msg}")
        return False, error_msg, {}


def list_recipients_in_period(
    folder: str,
    since_date: str,
    before_date: str,
    subject_contains: Optional[str] = None,
) -> Dict[str, Any]:
    """Lista destinatarios únicos en el período, con conteo y fecha del último envío."""
    _log(f"list_recipients_in_period folder={folder!r} {since_date}→{before_date}")
    ok, data, diag = _collect_recipients(folder, since_date, before_date, subject_contains)
    if not ok:
        return {"success": False, "error": data}

    recipients_list = [
        {"email": email, "count": info["count"], "last_date": info["last_date"]}
        for email, info in sorted(data.items())
    ]
    _log(f"list_recipients_in_period → {len(recipients_list)} destinatario(s) único(s)")

    result: Dict[str, Any] = {
        "success": True,
        "folder": folder,
        "since_date": since_date,
        "before_date": before_date,
        "total_recipients": len(recipients_list),
        "recipients": recipients_list,
    }
    if diag.get("sample_subjects") is not None and len(recipients_list) == 0 and subject_contains:
        result["diagnostic"] = {
            "hint": (
                f"0 emails encontrados con asunto que contenga {subject_contains!r}. "
                f"Sin filtro de asunto hay {diag['total_without_filter']} email(s) en el período."
            ),
            "sample_subjects": diag["sample_subjects"],
        }
    return result


def compare_periods(
    folder: str,
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    subject_contains: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compara destinatarios entre dos períodos.
    only_in_a = facturados en A pero no en B (pendientes del período actual).
    """
    subject_info = f" asunto={subject_contains!r}" if subject_contains else ""
    _log(
        f"compare_periods folder={folder!r}{subject_info} | "
        f"A: {period_a_start}→{period_a_end} | B: {period_b_start}→{period_b_end}"
    )

    ok_a, data_a, diag_a = _collect_recipients(folder, period_a_start, period_a_end, subject_contains)
    if not ok_a:
        return {"success": False, "error": f"Error al leer período A: {data_a}"}

    ok_b, data_b, diag_b = _collect_recipients(folder, period_b_start, period_b_end, subject_contains)
    if not ok_b:
        return {"success": False, "error": f"Error al leer período B: {data_b}"}

    set_a = set(data_a.keys())
    set_b = set(data_b.keys())
    only_in_a = sorted(set_a - set_b)
    only_in_b = sorted(set_b - set_a)
    in_both   = sorted(set_a & set_b)

    _log(
        f"compare_periods → A={len(set_a)} B={len(set_b)} | "
        f"solo_A={len(only_in_a)} solo_B={len(only_in_b)} ambos={len(in_both)}"
    )
    if only_in_a:
        _log(f"compare_periods → PENDIENTES (solo en A): {only_in_a}")
    else:
        _log("compare_periods → Sin pendientes: todos los de A ya están en B")

    result: Dict[str, Any] = {
        "success": True,
        "folder": folder,
        "period_a": {"start": period_a_start, "end": period_a_end, "total_recipients": len(set_a)},
        "period_b": {"start": period_b_start, "end": period_b_end, "total_recipients": len(set_b)},
        "only_in_a": only_in_a,
        "only_in_b": only_in_b,
        "in_both": in_both,
        "summary": {
            "in_a_not_b": len(only_in_a),
            "in_b_not_a": len(only_in_b),
            "in_both": len(in_both),
        },
    }

    # Diagnóstico: si ambos períodos dieron 0 con filtro de asunto, incluir muestra de asuntos reales
    if subject_contains and len(set_a) == 0 and len(set_b) == 0:
        subjects_found = diag_a.get("sample_subjects", []) or diag_b.get("sample_subjects", [])
        total_a = diag_a.get("total_without_filter", 0)
        total_b = diag_b.get("total_without_filter", 0)
        result["diagnostic"] = {
            "hint": (
                f"0 emails en ambos períodos con asunto que contenga {subject_contains!r}. "
                f"Sin filtro: período A={total_a} email(s), período B={total_b} email(s)."
            ),
            "sample_subjects": subjects_found,
        }
        _log(f"compare_periods → DIAGNÓSTICO: {result['diagnostic']}")

    return result


# ── Extracción de datos de facturas desde cuerpo del email ────────────────────

def _extract_invoice_data(body: str) -> Tuple[Optional[str], Optional[float]]:
    """
    Extrae (empresa, monto) del cuerpo de un email de documento electrónico.
    Formato esperado:
      ¡Estimado,  NOMBRE EMPRESA!
      ...
      Total Incl. Impuesto
         $141.31
    """
    company: Optional[str] = None
    amount: Optional[float] = None

    m = re.search(r'Estimado[,\s]{1,10}(.+?)[\s!¡\n\r]', body, re.IGNORECASE)
    if m:
        company = m.group(1).strip().rstrip('!¡').strip()

    m = re.search(
        r'Total\s+Incl\.?\s+Impuesto[\s\n\r]*\$?\s*([\d][0-9,\.]*)',
        body,
        re.IGNORECASE,
    )
    if m:
        try:
            amount = float(m.group(1).replace(',', ''))
        except ValueError:
            pass

    return company, amount


def list_invoices_in_period(
    since_date: str,
    before_date: str,
    subject_contains: Optional[str] = "Documento",
    limit: int = 200,
) -> Dict[str, Any]:
    """
    Busca emails en INBOX para el período dado, abre cada uno y extrae
    empresa + monto del cuerpo. Devuelve lista de facturas estructuradas.
    """
    _log(f"list_invoices_in_period {since_date}→{before_date} asunto={subject_contains!r} límite={limit}")
    try:
        from datetime import timedelta as _td

        mb = get_connection()
        mb.folder.set("INBOX")

        criteria_kwargs: Dict[str, Any] = {
            "date_gte": _parse_date(since_date),
            "date_lt": _parse_date(before_date),
        }
        if subject_contains:
            criteria_kwargs["subject"] = subject_contains

        criteria = _build_criteria(**criteria_kwargs)
        _log(f"list_invoices_in_period → criterio IMAP: {criteria}")

        safe_limit = limit if (limit and limit > 0) else 200
        invoices: List[Dict[str, Any]] = []
        for msg in mb.fetch(criteria, mark_seen=False, reverse=True, limit=safe_limit):
            body = msg.text or ""
            company, amount = _extract_invoice_data(body)
            invoices.append({
                "uid": msg.uid,
                "date": msg.date.isoformat()[:10] if msg.date else None,
                "company": company,
                "amount": amount,
                "subject": msg.subject,
                "from": msg.from_,
            })

        _log(f"list_invoices_in_period → {len(invoices)} factura(s) encontrada(s)")

        # Diagnóstico cuando no hay resultados
        diagnostic: Optional[Dict] = None
        if len(invoices) == 0:
            # Intentar sin filtro de asunto para ver qué hay en el período
            period_count = 0
            sample_subjects: List[str] = []
            if subject_contains:
                fallback_kwargs = {
                    "date_gte": _parse_date(since_date),
                    "date_lt": _parse_date(before_date),
                }
                for msg in mb.fetch(_build_criteria(**fallback_kwargs), mark_seen=False, headers_only=True, limit=20):
                    period_count += 1
                    if msg.subject and msg.subject not in sample_subjects and len(sample_subjects) < 10:
                        sample_subjects.append(msg.subject)
                _log(f"list_invoices_in_period → sin filtro asunto: {period_count} email(s), asuntos: {sample_subjects}")

            # Si el período está vacío, buscar últimos 2 meses sin filtro
            recent_emails: List[Dict] = []
            if period_count == 0:
                two_months_ago = (date.today().replace(day=1) - _td(days=1)).replace(day=1) - _td(days=1)
                two_months_ago = two_months_ago.replace(day=1)
                _log(f"list_invoices_in_period → período vacío. Buscando desde {two_months_ago} sin filtros...")
                for msg in mb.fetch(AND(date_gte=two_months_ago), mark_seen=False, reverse=True, limit=100):
                    recent_emails.append({
                        "date": msg.date.isoformat()[:10] if msg.date else "?",
                        "subject": (msg.subject or "")[:60],
                        "from": (msg.from_ or "")[:50],
                    })
                _log(f"list_invoices_in_period → emails últimos 2 meses: {len(recent_emails)}")

            if subject_contains and (sample_subjects or period_count > 0):
                hint = (
                    f"0 facturas encontradas con asunto que contenga {subject_contains!r} "
                    f"en el período {since_date} → {before_date}. "
                    f"Sin filtro de asunto hay {period_count} email(s) en ese período."
                )
                diagnostic = {"hint": hint, "sample_subjects": sample_subjects}
            elif recent_emails:
                hint = (
                    f"No hay emails en INBOX para el período {since_date} → {before_date}. "
                    f"Se encontraron {len(recent_emails)} email(s) en los últimos 2 meses."
                )
                diagnostic = {"hint": hint, "recent_emails": recent_emails}
            else:
                diagnostic = {"hint": f"El INBOX no tiene emails en los últimos 2 meses. Puede que el buzón esté vacío."}

        return {
            "success": True,
            "since_date": since_date,
            "before_date": before_date,
            "count": len(invoices),
            "invoices": invoices,
            **({"diagnostic": diagnostic} if diagnostic else {}),
        }
    except Exception as exc:
        _log(f"list_invoices_in_period ERROR: {exc}")
        return {"success": False, "error": str(exc)}


def compare_invoice_periods(
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    subject_contains: Optional[str] = "Documento",
) -> Dict[str, Any]:
    """
    Compara facturas entre dos períodos.
    Devuelve tabla comparativa y empresas presentes en A pero ausentes en B.
    """
    _log(
        f"compare_invoice_periods A:{period_a_start}→{period_a_end} "
        f"B:{period_b_start}→{period_b_end}"
    )

    res_a = list_invoices_in_period(period_a_start, period_a_end, subject_contains)
    if not res_a["success"]:
        return {"success": False, "error": f"Error al leer período A: {res_a['error']}"}

    res_b = list_invoices_in_period(period_b_start, period_b_end, subject_contains)
    if not res_b["success"]:
        return {"success": False, "error": f"Error al leer período B: {res_b['error']}"}

    inv_a: List[Dict] = res_a["invoices"]
    inv_b: List[Dict] = res_b["invoices"]

    # Agrupar por empresa (normalizado) → {empresa: {count, total, fechas}}
    def _group(invoices: List[Dict]) -> Dict[str, Dict]:
        grouped: Dict[str, Dict] = {}
        for inv in invoices:
            key = (inv.get("company") or "SIN EMPRESA").upper().strip()
            if key not in grouped:
                grouped[key] = {"count": 0, "total": 0.0, "dates": [], "display": inv.get("company") or "SIN EMPRESA"}
            grouped[key]["count"] += 1
            grouped[key]["total"] = round(grouped[key]["total"] + (inv.get("amount") or 0.0), 2)
            if inv.get("date"):
                grouped[key]["dates"].append(inv["date"])
        return grouped

    grp_a = _group(inv_a)
    grp_b = _group(inv_b)

    all_companies = sorted(set(grp_a) | set(grp_b))
    missing_in_b  = sorted(set(grp_a) - set(grp_b))
    new_in_b      = sorted(set(grp_b) - set(grp_a))
    in_both       = sorted(set(grp_a) & set(grp_b))

    table = []
    for co in all_companies:
        a = grp_a.get(co)
        b = grp_b.get(co)
        table.append({
            "company": (a or b)["display"],
            "period_a_count": a["count"] if a else 0,
            "period_a_total": a["total"] if a else None,
            "period_b_count": b["count"] if b else 0,
            "period_b_total": b["total"] if b else None,
            "status": "FALTA EN B" if co in missing_in_b else ("NUEVO EN B" if co in new_in_b else "OK"),
        })

    _log(
        f"compare_invoice_periods → empresas A={len(grp_a)} B={len(grp_b)} "
        f"faltantes={len(missing_in_b)} nuevas={len(new_in_b)}"
    )

    return {
        "success": True,
        "period_a": {"start": period_a_start, "end": period_a_end, "count": len(inv_a), "total": round(sum(i.get("amount") or 0 for i in inv_a), 2)},
        "period_b": {"start": period_b_start, "end": period_b_end, "count": len(inv_b), "total": round(sum(i.get("amount") or 0 for i in inv_b), 2)},
        "table": table,
        "missing_in_b": [grp_a[c]["display"] for c in missing_in_b],
        "new_in_b":     [grp_b[c]["display"] for c in new_in_b],
        "in_both":      [grp_a[c]["display"]  for c in in_both],
        "summary": {
            "total_companies": len(all_companies),
            "missing_in_b": len(missing_in_b),
            "new_in_b": len(new_in_b),
            "in_both": len(in_both),
        },
    }
