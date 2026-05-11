"""
Sincronización incremental IMAP → MySQL.

Flujo:
  1. Lee el último UID procesado desde imap_sync_estado.
  2. Busca TODOS los emails en INBOX con UID > ultimo_uid.
  3. Routing por asunto:
     - Asunto contiene 'Documento' → extrae XML adjunto → imap_facturas
     - Cualquier otro email      → guarda remitente/asunto/cuerpo → imap_comunicaciones
  4. Actualiza imap_sync_estado con el nuevo último UID.
"""

import re
import sys
from datetime import date
from typing import Optional

from imap_tools import AND

from . import imap_client as _ic
from .db import get_ultimo_uid, insert_comunicacion, insert_factura, update_sync_estado
from .xml_parser import parse_invoice_xml

TAG = "[IMAP_FACTURAS_SYNC]"


def _log(msg: str) -> None:
    print(f"{TAG} {msg}", file=sys.stderr, flush=True)


def _strip_html(html: str) -> str:
    """Elimina etiquetas HTML y normaliza espacios para guardar texto legible."""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html).strip()
    return html


def _extract_body(msg) -> Optional[str]:
    """Devuelve el texto del cuerpo del email (plain preferido, HTML como fallback)."""
    if msg.text and msg.text.strip():
        return msg.text.strip()[:4000]
    if msg.html and msg.html.strip():
        return _strip_html(msg.html)[:4000]
    return None


def sync_imap_facturas() -> dict:
    """
    Ejecuta la sincronización incremental. Diseñada para ser llamada por el cron.

    Retorna un resumen: {processed, facturas, comunicaciones, skipped, errors}.
    """
    ultimo_uid = get_ultimo_uid()
    _log(f"Iniciando sync — último UID procesado: {ultimo_uid}")

    uid_range = f"{ultimo_uid + 1}:*"

    try:
        mb = _ic.get_connection()
        mb.folder.set("INBOX")
    except Exception as exc:
        _log(f"ERROR conectando a IMAP: {exc}")
        return {"processed": 0, "facturas": 0, "comunicaciones": 0, "skipped": 0, "errors": 1}

    # Obtener headers de TODOS los emails nuevos (rápido, sin body)
    _log(f"Buscando todos los emails con UID {uid_range}")
    candidates = []
    try:
        for msg in mb.fetch(AND(uid=[uid_range]), mark_seen=False, headers_only=True):
            uid_int = int(msg.uid) if msg.uid else 0
            if uid_int > ultimo_uid:
                es_factura = "documento" in (msg.subject or "").lower()
                candidates.append((uid_int, msg.uid, es_factura))
    except Exception as exc:
        _log(f"ERROR buscando emails: {exc}")
        return {"processed": 0, "facturas": 0, "comunicaciones": 0, "skipped": 0, "errors": 1}

    if not candidates:
        _log("Sin emails nuevos")
        update_sync_estado(ultimo_uid)
        return {"processed": 0, "facturas": 0, "comunicaciones": 0, "skipped": 0, "errors": 0}

    candidates.sort(key=lambda x: x[0])
    n_fact = sum(1 for _, _, es_f in candidates if es_f)
    n_com  = len(candidates) - n_fact
    _log(f"{len(candidates)} email(s) nuevos: {n_fact} facturas, {n_com} comunicaciones")

    processed = facturas_ok = comunicaciones_ok = skipped = errors = 0
    max_uid_procesado = ultimo_uid

    for uid_int, uid_str, es_factura in candidates:
        try:
            msgs = list(mb.fetch(AND(uid=[uid_str]), mark_seen=False))
            if not msgs:
                _log(f"UID {uid_str}: no encontrado al refetch, saltando")
                skipped += 1
                max_uid_procesado = max(max_uid_procesado, uid_int)
                continue

            msg = msgs[0]
            processed += 1
            email_fecha = msg.date.date() if msg.date else date.today()
            asunto      = (msg.subject or "")[:499]

            if es_factura:
                # ── Flujo factura: buscar adjunto XML ─────────────────────
                xml_bytes: Optional[bytes] = None
                for att in msg.attachments:
                    name = (att.filename or "").upper()
                    if name.startswith("FACTURA_") and name.endswith(".XML"):
                        xml_bytes = att.payload
                        break

                parsed = parse_invoice_xml(xml_bytes) if xml_bytes else None

                if parsed:
                    ok = insert_factura(
                        email_uid=uid_str,
                        email_fecha=email_fecha,
                        doc_fecha=parsed.get("doc_fecha"),
                        doc_numero=parsed.get("doc_numero"),
                        empresa_ruc=parsed.get("empresa_ruc"),
                        empresa_nombre=parsed.get("empresa_nombre"),
                        subtotal=parsed.get("subtotal"),
                        iva=parsed.get("iva"),
                        total=parsed.get("total"),
                        tipo_doc=parsed.get("tipo_doc"),
                        asunto=asunto,
                        descripcion=parsed.get("descripcion"),
                        xml_ok=1,
                    )
                else:
                    reason = "sin adjunto XML" if not xml_bytes else "XML no parseado"
                    _log(f"UID {uid_str}: {reason} — guardando xml_ok=0")
                    ok = insert_factura(
                        email_uid=uid_str,
                        email_fecha=email_fecha,
                        doc_fecha=None, doc_numero=None,
                        empresa_ruc=None, empresa_nombre=None,
                        subtotal=None, iva=None, total=None,
                        tipo_doc=None, asunto=asunto,
                        descripcion=None, xml_ok=0,
                    )

                facturas_ok    += 1 if ok else 0
                skipped        += 0 if ok else 1

            else:
                # ── Flujo comunicación: guardar remitente/asunto/cuerpo ───
                de_email   = (msg.from_ or "")[:254] or None
                para_emails = ", ".join(msg.to)[:4000] or None
                cuerpo     = _extract_body(msg)

                ok = insert_comunicacion(
                    email_uid=uid_str,
                    email_fecha=email_fecha,
                    de_email=de_email,
                    para_emails=para_emails,
                    asunto=asunto,
                    cuerpo=cuerpo,
                )
                comunicaciones_ok += 1 if ok else 0
                skipped           += 0 if ok else 1

            max_uid_procesado = max(max_uid_procesado, uid_int)

        except Exception as exc:
            _log(f"UID {uid_str}: ERROR inesperado: {exc}")
            errors += 1
            max_uid_procesado = max(max_uid_procesado, uid_int)

    update_sync_estado(max_uid_procesado)
    _log(
        f"Sync completada — procesados={processed} "
        f"facturas={facturas_ok} comunicaciones={comunicaciones_ok} "
        f"duplicados={skipped} errores={errors} | nuevo último UID={max_uid_procesado}"
    )
    return {
        "processed":      processed,
        "facturas":       facturas_ok,
        "comunicaciones": comunicaciones_ok,
        "skipped":        skipped,
        "errors":         errors,
    }
