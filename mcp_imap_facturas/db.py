"""
Acceso a platform_db para el módulo mcp_imap_facturas.
Gestiona las tablas imap_facturas e imap_sync_estado.
"""

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import mysql.connector
from dotenv import load_dotenv

# Cargar variables desde el .env raíz del proyecto
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

_DB_CONFIG = {
    "host":     os.getenv("PLATFORM_DB_HOST", "localhost"),
    "port":     int(os.getenv("PLATFORM_DB_PORT", "3306")),
    "user":     os.getenv("PLATFORM_DB_USER", ""),
    "password": os.getenv("PLATFORM_DB_PASSWORD", ""),
    "database": os.getenv("PLATFORM_DB_DATABASE", "platform_db"),
    "charset":  "utf8mb4",
    "autocommit": True,
}

TAG = "[IMAP_FACTURAS_DB]"


def _log(msg: str) -> None:
    print(f"{TAG} {msg}", file=sys.stderr, flush=True)


def _get_conn():
    return mysql.connector.connect(**_DB_CONFIG)


# ── Sync estado ───────────────────────────────────────────────────────────────

def get_ultimo_uid() -> int:
    """Devuelve el último UID IMAP procesado (0 si nunca se ha sincronizado)."""
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT ultimo_uid FROM imap_sync_estado WHERE id = 1")
        row = cur.fetchone()
        return int(row["ultimo_uid"]) if row else 0
    finally:
        conn.close()


def update_sync_estado(ultimo_uid: int) -> None:
    """Actualiza el último UID procesado y la fecha de sincronización."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE imap_sync_estado SET ultimo_uid = %s, ultima_sync = NOW() WHERE id = 1",
            (str(ultimo_uid),),
        )
    finally:
        conn.close()


# ── Inserción de facturas ─────────────────────────────────────────────────────

def insert_factura(
    email_uid: str,
    email_fecha: date,
    doc_fecha: Optional[date],
    doc_numero: Optional[str],
    empresa_ruc: Optional[str],
    empresa_nombre: Optional[str],
    subtotal: Optional[float],
    iva: Optional[float],
    total: Optional[float],
    tipo_doc: Optional[str],
    asunto: Optional[str],
    descripcion: Optional[str],
    xml_ok: int,
) -> bool:
    """
    Inserta una factura. Retorna True si se insertó, False si ya existía (IGNORE).
    Si ya existe, actualiza descripcion si estaba vacía.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO imap_facturas
                (email_uid, email_fecha, doc_fecha, doc_numero,
                 empresa_ruc, empresa_nombre, subtotal, iva, total,
                 tipo_doc, asunto, descripcion, xml_ok)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                descripcion = IF(descripcion IS NULL AND VALUES(descripcion) IS NOT NULL,
                                 VALUES(descripcion), descripcion)
            """,
            (
                email_uid, email_fecha, doc_fecha, doc_numero,
                empresa_ruc, empresa_nombre, subtotal, iva, total,
                tipo_doc, asunto, descripcion, xml_ok,
            ),
        )
        inserted = cur.rowcount == 1
        _log(f"insert uid={email_uid} empresa={empresa_nombre!r} → {'OK' if inserted else 'YA EXISTE'}")
        return inserted
    finally:
        conn.close()


def insert_comunicacion(
    email_uid: str,
    email_fecha: date,
    de_email: Optional[str],
    para_emails: Optional[str],
    asunto: Optional[str],
    cuerpo: Optional[str],
) -> bool:
    """
    Inserta un email de comunicación (no factura). Retorna True si se insertó.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT IGNORE INTO imap_comunicaciones
                (email_uid, email_fecha, de_email, para_emails, asunto, cuerpo)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (email_uid, email_fecha, de_email, para_emails, asunto, cuerpo),
        )
        inserted = cur.rowcount > 0
        _log(f"comunicacion uid={email_uid} de={de_email!r} → {'OK' if inserted else 'YA EXISTE'}")
        return inserted
    finally:
        conn.close()


# ── Consultas para el agente ──────────────────────────────────────────────────

def facturas_en_periodo(
    since_date: str,
    before_date: str,
    empresa: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve facturas cuya fecha de documento cae en [since_date, before_date).
    Filtro opcional por nombre o RUC de empresa (búsqueda parcial, insensible a mayúsculas).
    """
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        if empresa:
            cur.execute(
                """
                SELECT doc_fecha, empresa_nombre, empresa_ruc,
                       subtotal, iva, total, tipo_doc, doc_numero, asunto, descripcion
                FROM   imap_facturas
                WHERE  doc_fecha >= %s AND doc_fecha < %s
                  AND  xml_ok = 1
                  AND  (empresa_nombre LIKE %s OR empresa_ruc LIKE %s)
                ORDER  BY doc_fecha DESC
                """,
                (since_date, before_date, f"%{empresa}%", f"%{empresa}%"),
            )
        else:
            cur.execute(
                """
                SELECT doc_fecha, empresa_nombre, empresa_ruc,
                       subtotal, iva, total, tipo_doc, doc_numero, asunto, descripcion
                FROM   imap_facturas
                WHERE  doc_fecha >= %s AND doc_fecha < %s
                  AND  xml_ok = 1
                ORDER  BY doc_fecha DESC
                """,
                (since_date, before_date),
            )
        return cur.fetchall()
    finally:
        conn.close()


def comunicaciones_en_periodo(
    since_date: str,
    before_date: str,
    empresa: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Devuelve emails de comunicación (no facturas) en [since_date, before_date).
    Filtro opcional por remitente o asunto (búsqueda parcial).
    """
    conn = _get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        if empresa:
            cur.execute(
                """
                SELECT email_fecha, de_email, para_emails, asunto, cuerpo
                FROM   imap_comunicaciones
                WHERE  email_fecha >= %s AND email_fecha < %s
                  AND  (de_email LIKE %s OR asunto LIKE %s)
                ORDER  BY email_fecha DESC
                """,
                (since_date, before_date, f"%{empresa}%", f"%{empresa}%"),
            )
        else:
            cur.execute(
                """
                SELECT email_fecha, de_email, para_emails, asunto, cuerpo
                FROM   imap_comunicaciones
                WHERE  email_fecha >= %s AND email_fecha < %s
                ORDER  BY email_fecha DESC
                """,
                (since_date, before_date),
            )
        return cur.fetchall()
    finally:
        conn.close()


def comparar_periodos(
    since_a: str, before_a: str,
    since_b: str, before_b: str,
) -> Dict[str, Any]:
    """
    Agrupa facturas por empresa para dos períodos y devuelve tabla comparativa.
    """
    def _agrupar(since: str, before: str) -> Dict[str, Dict]:
        rows = facturas_en_periodo(since, before)
        grouped: Dict[str, Dict] = {}
        for r in rows:
            key = (r["empresa_ruc"] or r["empresa_nombre"] or "SIN EMPRESA").upper().strip()
            if key not in grouped:
                grouped[key] = {
                    "display": r["empresa_nombre"] or r["empresa_ruc"] or "SIN EMPRESA",
                    "count": 0,
                    "total": 0.0,
                }
            grouped[key]["count"] += 1
            grouped[key]["total"] = round(grouped[key]["total"] + float(r["total"] or 0), 2)
        return grouped

    grp_a = _agrupar(since_a, before_a)
    grp_b = _agrupar(since_b, before_b)

    all_keys   = sorted(set(grp_a) | set(grp_b))
    missing_in_b = sorted(set(grp_a) - set(grp_b))
    new_in_b     = sorted(set(grp_b) - set(grp_a))
    in_both      = sorted(set(grp_a) & set(grp_b))

    table = []
    for key in all_keys:
        a = grp_a.get(key)
        b = grp_b.get(key)
        status = "FALTA EN B" if key in missing_in_b else ("NUEVO EN B" if key in new_in_b else "OK")
        table.append({
            "company":        (a or b)["display"],
            "period_a_count": a["count"] if a else 0,
            "period_a_total": a["total"] if a else None,
            "period_b_count": b["count"] if b else 0,
            "period_b_total": b["total"] if b else None,
            "status":         status,
        })

    return {
        "success": True,
        "period_a": {
            "start": since_a, "end": before_a,
            "count": sum(v["count"] for v in grp_a.values()),
            "total": round(sum(v["total"] for v in grp_a.values()), 2),
        },
        "period_b": {
            "start": since_b, "end": before_b,
            "count": sum(v["count"] for v in grp_b.values()),
            "total": round(sum(v["total"] for v in grp_b.values()), 2),
        },
        "table": table,
        "missing_in_b": [(grp_a[k]["display"]) for k in missing_in_b],
        "new_in_b":     [(grp_b[k]["display"]) for k in new_in_b],
        "in_both":      [(grp_a[k]["display"]) for k in in_both],
        "summary": {
            "total_companies": len(all_keys),
            "missing_in_b":    len(missing_in_b),
            "new_in_b":        len(new_in_b),
            "in_both":         len(in_both),
        },
    }
