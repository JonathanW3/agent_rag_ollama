"""
Cliente MySQL para platform_db.

Gestiona la conexión a la base de datos de autenticación/autorización
con pool de conexiones. Único punto de acceso a platform_db en toda la app.
"""

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from .config import settings

_pool: MySQLConnectionPool | None = None


def _get_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = MySQLConnectionPool(
            pool_name="platform_pool",
            pool_size=5,
            host=settings.PLATFORM_DB_HOST,
            port=settings.PLATFORM_DB_PORT,
            user=settings.PLATFORM_DB_USER,
            password=settings.PLATFORM_DB_PASSWORD,
            database=settings.PLATFORM_DB_DATABASE,
            charset="utf8mb4",
            autocommit=True,
        )
    return _pool


def _get_conn():
    return _get_pool().get_connection()


# ---------------------------------------------------------------------------
# Consultas de autenticación
# ---------------------------------------------------------------------------

def get_org_by_key_hash(key_hash: str) -> dict | None:
    """
    Busca una organización activa por el hash SHA-256 de su API key.
    Consulta la vista v_active_keys que filtra claves y orgs activas/no expiradas.
    Retorna el registro completo o None si no existe/está inactiva.
    """
    sql = """
        SELECT api_key_id, key_hash, key_label, last_used_at, expires_at,
               org_id, org_name, company_lic_cod, max_agents, org_active,
               is_admin
        FROM v_active_keys
        WHERE key_hash = %s
        LIMIT 1
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (key_hash,))
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


def update_key_last_used(api_key_id: int) -> None:
    """Actualiza last_used_at de una API key. Se llama tras autenticación exitosa."""
    sql = "UPDATE api_keys SET last_used_at = NOW() WHERE id = %s"
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (api_key_id,))
        cursor.close()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gestión de organizaciones
# ---------------------------------------------------------------------------

def create_organization(name: str, company_lic_cod: str, api_key: str,
                        key_hash: str, label: str = "default") -> dict:
    """
    Crea una organización y su primera API key usando el stored procedure.
    Retorna {org_id, api_key_id, company_lic_cod}.
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.callproc("sp_create_organization",
                        (name, company_lic_cod, api_key, key_hash, label))
        result = {}
        for res in cursor.stored_results():
            result = res.fetchone() or {}
        cursor.close()
        return result
    finally:
        conn.close()


def get_organization(company_lic_cod: str) -> dict | None:
    """Obtiene una organización por su company_lic_cod."""
    sql = """
        SELECT id, name, company_lic_cod, is_active, max_agents, created_at, updated_at
        FROM organizations
        WHERE company_lic_cod = %s
        LIMIT 1
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (company_lic_cod,))
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


def list_organizations() -> list[dict]:
    """Lista todas las organizaciones (sin datos sensibles)."""
    sql = """
        SELECT id, name, company_lic_cod, is_active, max_agents, created_at, updated_at
        FROM organizations
        ORDER BY name
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def set_organization_active(org_id: int, is_active: bool) -> None:
    """Activa o suspende una organización."""
    sql = "UPDATE organizations SET is_active = %s WHERE id = %s"
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (1 if is_active else 0, org_id))
        cursor.close()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Gestión de API keys
# ---------------------------------------------------------------------------

def create_api_key(org_id: int, api_key: str, key_hash: str,
                   label: str = "default") -> dict:
    """Agrega una nueva API key a una organización existente."""
    sql = """
        INSERT INTO api_keys (org_id, label, api_key, key_hash)
        VALUES (%s, %s, %s, %s)
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (org_id, label, api_key, key_hash))
        new_id = cursor.lastrowid
        cursor.close()
        return {"api_key_id": new_id, "org_id": org_id, "label": label}
    finally:
        conn.close()


def list_api_keys(org_id: int) -> list[dict]:
    """Lista las API keys de una organización (sin exponer el secreto plano)."""
    sql = """
        SELECT id, label, is_active, last_used_at, expires_at, created_at, revoked_at
        FROM api_keys
        WHERE org_id = %s
        ORDER BY created_at DESC
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (org_id,))
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def revoke_api_key(api_key_id: int, org_id: int) -> bool:
    """
    Revoca una API key verificando que pertenezca a la organización indicada.
    Retorna True si se revocó, False si no existía o no pertenece a la org.
    """
    sql = """
        UPDATE api_keys
        SET is_active = 0, revoked_at = NOW()
        WHERE id = %s AND org_id = %s AND is_active = 1
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (api_key_id, org_id))
        affected = cursor.rowcount
        cursor.close()
        return affected > 0
    finally:
        conn.close()


def rotate_api_key(old_api_key_id: int, new_api_key: str,
                   new_key_hash: str, label: str = "rotada") -> dict:
    """Revoca la clave vieja y crea una nueva usando el stored procedure."""
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.callproc("sp_rotate_api_key",
                        (old_api_key_id, new_api_key, new_key_hash, label))
        result = {}
        for res in cursor.stored_results():
            result = res.fetchone() or {}
        cursor.close()
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Auditoría
# ---------------------------------------------------------------------------

def write_audit_log(entity_type: str, action: str, org_id: int | None = None,
                    api_key_id: int | None = None, entity_id: str | None = None,
                    ip_address: str | None = None, user_agent: str | None = None,
                    meta: dict | None = None) -> None:
    """
    Inserta un registro en audit_log. Fire-and-forget: los errores se suprimen
    para no interrumpir el flujo de negocio.
    """
    import json as _json
    sql = """
        INSERT INTO audit_log
            (org_id, api_key_id, entity_type, entity_id, action,
             ip_address, user_agent, meta)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        conn = _get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (
                org_id, api_key_id, entity_type, entity_id, action,
                ip_address, user_agent,
                _json.dumps(meta, default=str) if meta else None
            ))
            cursor.close()
        finally:
            conn.close()
    except Exception:
        pass  # Auditoría nunca rompe el flujo principal
