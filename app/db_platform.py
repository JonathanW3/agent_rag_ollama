"""
Cliente MySQL para platform_db.

Gestiona la conexión a la base de datos de autenticación/autorización
con pool de conexiones. Único punto de acceso a platform_db en toda la app.
"""

import json as _json
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


# ---------------------------------------------------------------------------
# Cron de licencias
# ---------------------------------------------------------------------------

def list_cron_licencias(only_active: bool = False) -> list[dict]:
    """Lista todas las configuraciones de cron de licencias."""
    sql = "SELECT * FROM cron_licencias"
    if only_active:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY agent_id"
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def get_cron_licencias(agent_id: str) -> dict | None:
    """Obtiene la configuración de cron de un agente específico."""
    sql = "SELECT * FROM cron_licencias WHERE agent_id = %s LIMIT 1"
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (agent_id,))
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


def migrate_cron_licencias() -> None:
    """Agrega columnas de notificación WhatsApp a cron_licencias si no existen (MySQL compatible)."""
    import logging as _logging
    log = _logging.getLogger("db_platform")

    new_columns = [
        ("wa_notify_phone",   "VARCHAR(50)  NULL"),
        ("wa_notify_session", "VARCHAR(100) NULL"),
    ]
    check_sql = """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'cron_licencias'
          AND COLUMN_NAME  = %s
    """
    conn = _get_conn()
    try:
        for col_name, col_def in new_columns:
            cursor = conn.cursor()
            cursor.execute(check_sql, (col_name,))
            (exists,) = cursor.fetchone()
            cursor.close()
            if not exists:
                cursor = conn.cursor()
                cursor.execute(f"ALTER TABLE cron_licencias ADD COLUMN {col_name} {col_def}")
                cursor.close()
                log.info(f"migrate_cron_licencias: columna '{col_name}' agregada")
    except Exception as e:
        log.warning(f"migrate_cron_licencias: {e}")
    finally:
        conn.close()


def upsert_cron_licencias(
    agent_id: str,
    session_id: str = "licencias_diario",
    hora: int = 8,
    minuto: int = 0,
    timezone: str = "America/Guayaquil",
    dias: int = 30,
    ttl: int = 604800,
    is_active: bool = True,
    wa_notify_phone: str | None = None,
    wa_notify_session: str | None = None,
) -> dict:
    """Crea o actualiza la configuración de cron para un agente. Retorna el registro resultante."""
    sql = """
        INSERT INTO cron_licencias
            (agent_id, session_id, hora, minuto, timezone, dias, ttl, is_active,
             wa_notify_phone, wa_notify_session)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            session_id        = VALUES(session_id),
            hora              = VALUES(hora),
            minuto            = VALUES(minuto),
            timezone          = VALUES(timezone),
            dias              = VALUES(dias),
            ttl               = VALUES(ttl),
            is_active         = VALUES(is_active),
            wa_notify_phone   = VALUES(wa_notify_phone),
            wa_notify_session = VALUES(wa_notify_session),
            updated_at        = NOW()
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (
            agent_id, session_id, hora, minuto, timezone, dias, ttl,
            1 if is_active else 0,
            wa_notify_phone or None,
            wa_notify_session or None,
        ))
        cursor.close()
    finally:
        conn.close()
    return get_cron_licencias(agent_id)


def set_cron_licencias_active(agent_id: str, is_active: bool) -> bool:
    """Activa o suspende el cron de un agente. Retorna True si el registro existía."""
    sql = "UPDATE cron_licencias SET is_active = %s, updated_at = NOW() WHERE agent_id = %s"
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (1 if is_active else 0, agent_id))
        affected = cursor.rowcount
        cursor.close()
        return affected > 0
    finally:
        conn.close()


def delete_cron_licencias(agent_id: str) -> bool:
    """Elimina la configuración de cron de un agente. Retorna True si existía."""
    sql = "DELETE FROM cron_licencias WHERE agent_id = %s"
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (agent_id,))
        affected = cursor.rowcount
        cursor.close()
        return affected > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Log de ejecuciones del cron
# ---------------------------------------------------------------------------

def insert_cron_log(
    agent_id: str,
    success: bool,
    total_licencias: int | None = None,
    duracion_ms: int | None = None,
    reporte: str | None = None,
    error: str | None = None,
) -> None:
    """Registra una ejecución del cron. Fire-and-forget: los errores se suprimen."""
    sql = """
        INSERT INTO cron_licencias_log
            (agent_id, success, total_licencias, duracion_ms, reporte, error)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    try:
        conn = _get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (
                agent_id,
                1 if success else 0,
                total_licencias,
                duracion_ms,
                reporte,
                error,
            ))
            cursor.close()
        finally:
            conn.close()
    except Exception:
        pass  # El log nunca rompe el flujo principal


def list_cron_logs(agent_id: str, limit: int = 50) -> list[dict]:
    """Devuelve el historial de ejecuciones de un agente, del más reciente al más antiguo."""
    sql = """
        SELECT id, agent_id, executed_at, success,
               total_licencias, duracion_ms,
               LEFT(reporte, 500) AS reporte_resumen,
               error
        FROM cron_licencias_log
        WHERE agent_id = %s
        ORDER BY executed_at DESC
        LIMIT %s
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (agent_id, limit))
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def get_cron_log_detail(log_id: int) -> dict | None:
    """Devuelve el reporte completo de una ejecución específica."""
    sql = "SELECT * FROM cron_licencias_log WHERE id = %s LIMIT 1"
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (log_id,))
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cron Meta-Agente  (configuración y logs por sub-agente vinculado a Meta)
# ---------------------------------------------------------------------------

def migrate_cron_meta_agent() -> None:
    """Crea las tablas cron_meta_agent y cron_meta_agent_log si no existen."""
    import logging as _logging
    log = _logging.getLogger("db_platform")

    create_config = """
        CREATE TABLE IF NOT EXISTS cron_meta_agent (
            id                INT UNSIGNED  NOT NULL AUTO_INCREMENT,
            agent_id          VARCHAR(100)  NOT NULL
                COMMENT 'ID del sub-agente (LicenciasEC, CorreosEC, etc.)',
            query             TEXT          NOT NULL
                COMMENT 'Consulta predefinida que se ejecutará en cada disparo',
            session_id        VARCHAR(100)  NOT NULL DEFAULT 'cron_meta'
                COMMENT 'ID de sesión Redis para el historial',
            hora              TINYINT       NOT NULL DEFAULT 8,
            minuto            TINYINT       NOT NULL DEFAULT 0,
            timezone          VARCHAR(50)   NOT NULL DEFAULT 'America/Guayaquil',
            dedup_strategy    VARCHAR(20)   NOT NULL DEFAULT 'hash'
                COMMENT 'hash | date | none',
            dedup_ttl         INT           NOT NULL DEFAULT 82800
                COMMENT 'TTL del hash Redis en segundos (default 23 h)',
            is_active         TINYINT(1)    NOT NULL DEFAULT 1,
            wa_notify_phones  TEXT          DEFAULT NULL
                COMMENT 'JSON array de números destino, ej: ["5930987654321","5931234567890"]',
            wa_notify_session VARCHAR(100)  DEFAULT NULL,
            created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            UNIQUE KEY uk_cron_meta_agent_id (agent_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Configuración del cron por sub-agente vinculado al meta-agente'
    """
    create_log = """
        CREATE TABLE IF NOT EXISTS cron_meta_agent_log (
            id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
            agent_id     VARCHAR(100)    NOT NULL,
            executed_at  DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
            success      TINYINT(1)      NOT NULL,
            enviado_wa   TINYINT(1)      NOT NULL DEFAULT 0
                COMMENT '1 si se envió alerta WhatsApp',
            dedup_skip   TINYINT(1)      NOT NULL DEFAULT 0
                COMMENT '1 si se omitió por deduplicación',
            duracion_ms  INT UNSIGNED    DEFAULT NULL,
            reporte      MEDIUMTEXT      DEFAULT NULL,
            error        TEXT            DEFAULT NULL,
            PRIMARY KEY (id),
            KEY idx_cma_log_agent (agent_id),
            KEY idx_cma_log_time  (executed_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
          COMMENT='Historial de ejecuciones del cron del meta-agente'
    """
    def _exec(sql: str) -> None:
        c = _get_conn()
        try:
            cur = c.cursor()
            cur.execute(sql)
            cur.fetchall()
            cur.close()
        finally:
            c.close()

    def _fetchone(sql: str) -> tuple:
        c = _get_conn()
        try:
            cur = c.cursor()
            cur.execute(sql)
            row = cur.fetchone()
            cur.fetchall()
            cur.close()
            return row or (0,)
        finally:
            c.close()

    try:
        _exec(create_config)
        _exec(create_log)
        (has_old,) = _fetchone("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'cron_meta_agent'
              AND COLUMN_NAME  = 'wa_notify_phone'
        """)
        if has_old:
            _exec("""
                ALTER TABLE cron_meta_agent
                ADD COLUMN wa_notify_phones TEXT DEFAULT NULL
                    COMMENT 'JSON array de números destino'
                AFTER wa_notify_phone
            """)
            _exec("""
                UPDATE cron_meta_agent
                SET wa_notify_phones = JSON_ARRAY(wa_notify_phone)
                WHERE wa_notify_phone IS NOT NULL
            """)
            _exec("ALTER TABLE cron_meta_agent DROP COLUMN wa_notify_phone")
            log.info("[DB] Migrado wa_notify_phone → wa_notify_phones (JSON array)")
        log.info("[DB] Tablas cron_meta_agent y cron_meta_agent_log verificadas/creadas")
    except Exception as e:
        log.error(f"[DB] Error en migrate_cron_meta_agent: {e}")


def _deserialize_cron_row(row: dict) -> dict:
    if row and "wa_notify_phones" in row:
        val = row["wa_notify_phones"]
        if isinstance(val, str):
            try:
                row["wa_notify_phones"] = _json.loads(val)
            except Exception:
                row["wa_notify_phones"] = [val] if val else []
        elif val is None:
            row["wa_notify_phones"] = []
    return row


def list_cron_meta_agent(only_active: bool = False) -> list[dict]:
    sql = "SELECT * FROM cron_meta_agent"
    if only_active:
        sql += " WHERE is_active = 1"
    sql += " ORDER BY agent_id"
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        return [_deserialize_cron_row(r) for r in (rows or [])]
    finally:
        conn.close()


def get_cron_meta_agent(agent_id: str) -> dict | None:
    sql = "SELECT * FROM cron_meta_agent WHERE agent_id = %s LIMIT 1"
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (agent_id,))
        row = cursor.fetchone()
        cursor.close()
        return _deserialize_cron_row(row) if row else None
    finally:
        conn.close()


def upsert_cron_meta_agent(
    agent_id: str,
    query: str,
    session_id: str = "cron_meta",
    hora: int = 8,
    minuto: int = 0,
    timezone: str = "America/Guayaquil",
    dedup_strategy: str = "hash",
    dedup_ttl: int = 82800,
    is_active: bool = True,
    wa_notify_phones: list[str] | None = None,
    wa_notify_session: str | None = None,
) -> dict:
    phones_json = _json.dumps(wa_notify_phones) if wa_notify_phones else None
    sql = """
        INSERT INTO cron_meta_agent
            (agent_id, query, session_id, hora, minuto, timezone,
             dedup_strategy, dedup_ttl, is_active, wa_notify_phones, wa_notify_session)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            query             = VALUES(query),
            session_id        = VALUES(session_id),
            hora              = VALUES(hora),
            minuto            = VALUES(minuto),
            timezone          = VALUES(timezone),
            dedup_strategy    = VALUES(dedup_strategy),
            dedup_ttl         = VALUES(dedup_ttl),
            is_active         = VALUES(is_active),
            wa_notify_phones  = VALUES(wa_notify_phones),
            wa_notify_session = VALUES(wa_notify_session),
            updated_at        = NOW()
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (
            agent_id, query, session_id, hora, minuto, timezone,
            dedup_strategy, dedup_ttl,
            1 if is_active else 0,
            phones_json,
            wa_notify_session or None,
        ))
        cursor.close()
    finally:
        conn.close()
    return get_cron_meta_agent(agent_id)


def set_cron_meta_agent_active(agent_id: str, is_active: bool) -> bool:
    sql = "UPDATE cron_meta_agent SET is_active = %s, updated_at = NOW() WHERE agent_id = %s"
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (1 if is_active else 0, agent_id))
        affected = cursor.rowcount
        cursor.close()
        return affected > 0
    finally:
        conn.close()


def delete_cron_meta_agent(agent_id: str) -> bool:
    sql = "DELETE FROM cron_meta_agent WHERE agent_id = %s"
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (agent_id,))
        affected = cursor.rowcount
        cursor.close()
        return affected > 0
    finally:
        conn.close()


def insert_cron_meta_agent_log(
    agent_id: str,
    success: bool,
    enviado_wa: bool = False,
    dedup_skip: bool = False,
    duracion_ms: int | None = None,
    reporte: str | None = None,
    error: str | None = None,
) -> None:
    sql = """
        INSERT INTO cron_meta_agent_log
            (agent_id, success, enviado_wa, dedup_skip, duracion_ms, reporte, error)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    try:
        conn = _get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, (
                agent_id,
                1 if success else 0,
                1 if enviado_wa else 0,
                1 if dedup_skip else 0,
                duracion_ms,
                reporte,
                error,
            ))
            cursor.close()
        finally:
            conn.close()
    except Exception:
        pass


def list_cron_meta_agent_logs(agent_id: str, limit: int = 50) -> list[dict]:
    sql = """
        SELECT id, agent_id, executed_at, success, enviado_wa, dedup_skip,
               duracion_ms, LEFT(reporte, 500) AS reporte_resumen, error
        FROM cron_meta_agent_log
        WHERE agent_id = %s
        ORDER BY executed_at DESC
        LIMIT %s
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (agent_id, limit))
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def get_cron_meta_agent_log_detail(log_id: int) -> dict | None:
    sql = "SELECT * FROM cron_meta_agent_log WHERE id = %s LIMIT 1"
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (log_id,))
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Licencias Ecuador (espejo de SQL Server en platform_db)
# ---------------------------------------------------------------------------

def migrate_licencias_ecuador() -> None:
    """Crea la tabla licencias_ecuador si no existe y agrega columnas nuevas si faltan."""
    import logging as _logging
    log = _logging.getLogger("db_platform")

    create_sql = """
        CREATE TABLE IF NOT EXISTS licencias_ecuador (
            CompanyRUC                VARCHAR(50)  NOT NULL,
            CompanyName               VARCHAR(255) NULL,
            Country                   VARCHAR(100) NULL,
            ContactEmail              VARCHAR(255) NULL,
            TotalLicencias            INT          NOT NULL DEFAULT 0,
            EFiscalDocsCount          INT          NOT NULL DEFAULT 0,
            EFiscalDocsExpirationDate DATE         NULL,
            MinExpirationDate         DATE         NULL,
            MinSwSExpirationDate      DATE         NULL,
            LicenciasJSON             LONGTEXT     NULL,
            Licenciamiento            TINYINT(1)   NOT NULL DEFAULT 0,
            synced_at                 DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                   ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (CompanyRUC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    extra_columns = [
        ("MinExpirationDate",    "DATE NULL"),
        ("MinSwSExpirationDate", "DATE NULL"),
    ]
    check_col_sql = """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'licencias_ecuador'
          AND COLUMN_NAME  = %s
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(create_sql)
        cursor.close()
        for col_name, col_def in extra_columns:
            cursor = conn.cursor()
            cursor.execute(check_col_sql, (col_name,))
            (exists,) = cursor.fetchone()
            cursor.close()
            if not exists:
                cursor = conn.cursor()
                cursor.execute(f"ALTER TABLE licencias_ecuador ADD COLUMN {col_name} {col_def}")
                cursor.close()
                log.info(f"migrate_licencias_ecuador: columna '{col_name}' agregada")
        log.info("migrate_licencias_ecuador: tabla lista")
    except Exception as e:
        log.warning(f"migrate_licencias_ecuador: {e}")
    finally:
        conn.close()


def _min_date_from_licencias(licencias_json, field: str) -> str | None:
    """Extrae la fecha mínima de un campo de LicenciasJSON. Retorna YYYY-MM-DD o None."""
    import json as _json
    if not licencias_json:
        return None
    if isinstance(licencias_json, str):
        try:
            licencias = _json.loads(licencias_json)
        except Exception:
            return None
    else:
        licencias = licencias_json
    dates = []
    for lic in licencias:
        val = lic.get(field)
        if val and isinstance(val, str) and len(val) >= 10 and val[:4].isdigit():
            dates.append(val[:10])
    return min(dates) if dates else None


def upsert_licencias_ecuador(rows: list[dict]) -> int:
    """
    Upsert de filas provenientes del query SQL Server.
    Preserva el campo Licenciamiento en registros existentes.
    Retorna la cantidad de filas procesadas.
    """
    import json as _json

    sql = """
        INSERT INTO licencias_ecuador
            (CompanyRUC, CompanyName, Country, ContactEmail,
             TotalLicencias, EFiscalDocsCount, EFiscalDocsExpirationDate,
             MinExpirationDate, MinSwSExpirationDate,
             LicenciasJSON, Licenciamiento, synced_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, NOW())
        ON DUPLICATE KEY UPDATE
            CompanyName               = VALUES(CompanyName),
            Country                   = VALUES(Country),
            ContactEmail              = VALUES(ContactEmail),
            TotalLicencias            = VALUES(TotalLicencias),
            EFiscalDocsCount          = VALUES(EFiscalDocsCount),
            EFiscalDocsExpirationDate = VALUES(EFiscalDocsExpirationDate),
            MinExpirationDate         = VALUES(MinExpirationDate),
            MinSwSExpirationDate      = VALUES(MinSwSExpirationDate),
            LicenciasJSON             = VALUES(LicenciasJSON),
            synced_at                 = NOW()
    """
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        for row in rows:
            licencias_json_raw = row.get("LicenciasJSON")
            licencias_json_str = (
                _json.dumps(licencias_json_raw, ensure_ascii=False, default=str)
                if licencias_json_raw is not None and not isinstance(licencias_json_raw, str)
                else licencias_json_raw
            )
            efiscal_date = (row.get("EFiscalDocsExpirationDate") or "")[:10] or None
            min_exp  = _min_date_from_licencias(licencias_json_raw, "ExpirationDate")
            min_sws  = _min_date_from_licencias(licencias_json_raw, "SwSExpirationDate")

            cursor.execute(sql, (
                row.get("CompanyRUC"),
                row.get("CompanyName"),
                row.get("Country"),
                row.get("ContactEmail"),
                int(row.get("TotalLicencias") or 0),
                int(row.get("EFiscalDocsCount") or 0),
                efiscal_date,
                min_exp,
                min_sws,
                licencias_json_str,
            ))
        cursor.close()
        return len(rows)
    finally:
        conn.close()


def set_licenciamiento(company_ruc: str, licenciamiento: bool) -> bool:
    """
    Establece el flag Licenciamiento de una empresa.
    True  = Licenciamiento (instalación local)
    False = Nube
    Retorna True si el registro existía.
    """
    sql = "UPDATE licencias_ecuador SET Licenciamiento = %s WHERE CompanyRUC = %s"
    conn = _get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (1 if licenciamiento else 0, company_ruc))
        affected = cursor.rowcount
        cursor.close()
        return affected > 0
    finally:
        conn.close()


def resumen_tipo_licenciamiento(licenciamiento: bool | None = None) -> list[dict]:
    """
    Retorna un resumen liviano de empresas Ecuador sin LicenciasJSON.
    Campos: CompanyRUC, CompanyName, ContactEmail, TotalLicencias,
            EFiscalDocsCount, EFiscalDocsExpirationDate,
            MinExpirationDate, MinSwSExpirationDate, Licenciamiento, synced_at.
    licenciamiento: True=on-premise, False=Nube, None=todos.
    """
    sql = """
        SELECT CompanyRUC, CompanyName, ContactEmail,
               TotalLicencias, EFiscalDocsCount,
               EFiscalDocsExpirationDate,
               MinExpirationDate, MinSwSExpirationDate,
               Licenciamiento, synced_at
        FROM licencias_ecuador
    """
    params: list = []
    if licenciamiento is not None:
        sql += " WHERE Licenciamiento = %s"
        params.append(1 if licenciamiento else 0)
    sql += " ORDER BY CompanyName"

    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def buscar_licencias_ecuador(
    nombre: str = "",
    ruc: str = "",
    licenciamiento: bool | None = None,
) -> list[dict]:
    """
    Busca empresas en licencias_ecuador.
    - nombre: búsqueda parcial LIKE en CompanyName
    - ruc: búsqueda parcial LIKE en CompanyRUC
    - licenciamiento: True=Licenciamiento, False=Nube, None=todos
    """
    conditions: list[str] = []
    params: list = []

    if nombre:
        conditions.append("CompanyName LIKE %s")
        params.append(f"%{nombre}%")
    if ruc:
        conditions.append("CompanyRUC LIKE %s")
        params.append(f"%{ruc}%")
    if licenciamiento is not None:
        conditions.append("Licenciamiento = %s")
        params.append(1 if licenciamiento else 0)

    sql = "SELECT * FROM licencias_ecuador"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY CompanyName"

    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows or []
    finally:
        conn.close()


def get_licencias_por_vencer(dias: int = 30, campo: str = "ambas") -> list[dict]:
    """
    Retorna licencias individuales (desde LicenciasJSON) que vencen en los
    próximos `dias` días. Agrega DiasParaExpiracion y DiasParaSwSExpiracion.
    campo: 'ExpirationDate' | 'SwSExpirationDate' | 'ambas'
    """
    import json as _json
    from datetime import date as _date, timedelta as _td

    today  = _date.today()
    cutoff = today + _td(days=dias)

    all_companies = buscar_licencias_ecuador()
    result: list[dict] = []

    for company in all_companies:
        raw = company.get("LicenciasJSON")
        if isinstance(raw, str):
            try:
                licencias = _json.loads(raw)
            except Exception:
                continue
        elif isinstance(raw, list):
            licencias = raw
        else:
            continue

        for lic in licencias:
            exp_str = (lic.get("ExpirationDate") or "")[:10]
            sws_str = (lic.get("SwSExpirationDate") or "")[:10]
            try:
                exp_d = _date.fromisoformat(exp_str) if exp_str else None
            except ValueError:
                exp_d = None
            try:
                sws_d = _date.fromisoformat(sws_str) if sws_str else None
            except ValueError:
                sws_d = None

            exp_match = campo in ("ambas", "ExpirationDate")    and exp_d and today <= exp_d <= cutoff
            sws_match = campo in ("ambas", "SwSExpirationDate") and sws_d and today <= sws_d <= cutoff
            if not (exp_match or sws_match):
                continue

            result.append({
                "CompanyRUC":            lic.get("CompanyRUC")    or company.get("CompanyRUC"),
                "CompanyName":           lic.get("CompanyName")   or company.get("CompanyName"),
                "ExpirationDate":        exp_str or None,
                "SwSExpirationDate":     sws_str or None,
                "LicStatus":             lic.get("LicStatus"),
                "SubProduct":            lic.get("SubProduct"),
                "QtyOfUsers":            lic.get("QtyOfUsers"),
                "Technician":            lic.get("Technician"),
                "ContactName":           lic.get("ContactName"),
                "ContactEmail":          lic.get("ContactEmail") or company.get("ContactEmail"),
                "Licenciamiento":        bool(company.get("Licenciamiento")),
                "DiasParaExpiracion":    (exp_d - today).days if exp_d else None,
                "DiasParaSwSExpiracion": (sws_d - today).days if sws_d else None,
            })

    result.sort(key=lambda x: min(
        x["DiasParaExpiracion"]    if x["DiasParaExpiracion"]    is not None else 9999,
        x["DiasParaSwSExpiracion"] if x["DiasParaSwSExpiracion"] is not None else 9999,
    ))
    return result


def get_licencias_efiscal_por_mes(dias: int = 45) -> list[dict]:
    """
    Retorna empresas con Licenciamiento=1 cuyo EFiscalDocsExpirationDate
    tiene un mes que cae dentro del rango de los próximos `dias` días.
    El año del campo es ignorado; solo importa el mes.
    Agrega DiasParaVencer y ProximaFechaVencimiento (calculados al año actual o siguiente).
    """
    from datetime import date as _date, timedelta as _td

    today    = _date.today()
    end_date = today + _td(days=dias)

    # Meses que cubre la ventana (maneja cruce de año)
    months_in_range: set[int] = set()
    cur = today
    while cur <= end_date:
        months_in_range.add(cur.month)
        cur = (cur.replace(day=1) + _td(days=32)).replace(day=1)

    companies = buscar_licencias_ecuador(licenciamiento=True)
    result: list[dict] = []

    for c in companies:
        raw_exp = c.get("EFiscalDocsExpirationDate")
        if not raw_exp:
            continue

        if isinstance(raw_exp, str):
            try:
                exp_date = _date.fromisoformat(raw_exp[:10])
            except ValueError:
                continue
        else:
            exp_date = raw_exp  # datetime.date desde MySQL

        if exp_date.month not in months_in_range:
            continue

        # Próxima ocurrencia de ese mes/día (este año o siguiente si ya pasó)
        try:
            proxima = exp_date.replace(year=today.year)
        except ValueError:
            proxima = exp_date.replace(year=today.year, day=28)
        if proxima < today:
            try:
                proxima = proxima.replace(year=today.year + 1)
            except ValueError:
                proxima = proxima.replace(year=today.year + 1, day=28)

        result.append({
            **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in c.items()},
            "MesVencimiento":          exp_date.month,
            "DiasParaVencer":          (proxima - today).days,
            "ProximaFechaVencimiento": proxima.isoformat(),
        })

    result.sort(key=lambda x: x["DiasParaVencer"])
    return result


def list_licencias_ecuador(solo_licenciamiento: bool | None = None) -> list[dict]:
    """Lista empresas de licencias_ecuador. Filtro opcional por Licenciamiento."""
    return buscar_licencias_ecuador(licenciamiento=solo_licenciamiento)


def get_licencia_ecuador(company_ruc: str) -> dict | None:
    """Obtiene el registro de una empresa por su CompanyRUC."""
    sql = "SELECT * FROM licencias_ecuador WHERE CompanyRUC = %s LIMIT 1"
    conn = _get_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (company_ruc,))
        row = cursor.fetchone()
        cursor.close()
        return row
    finally:
        conn.close()
