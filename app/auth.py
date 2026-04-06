"""
Middleware de autenticación por API Key.

Flujo por request:
  1. Lee header X-API-Key
  2. Calcula SHA-256 del valor
  3. Busca en Redis cache (TTL 5 min) → hit: usa org cacheada
  4. Si miss: consulta MySQL v_active_keys → guarda en cache → usa org
  5. Si no existe o está inactiva → 401
  6. Escribe audit_log de forma asíncrona (fire-and-forget)

Uso en routers:
  from ..auth import get_current_org, OrgContext

  @router.post("/agents")
  def create_agent(req: AgentCreate, org: OrgContext = Depends(get_current_org)):
      ...
"""

import hashlib
import json
from typing import Annotated
from fastapi import Depends, Header, HTTPException, Request
from .redis_client import get_redis_client
from .db_platform import get_org_by_key_hash, update_key_last_used, write_audit_log
from .config import settings

# Alias de tipo para anotar dependencias en routers
OrgContext = dict

# TTL del cache Redis para autenticación (5 minutos)
_AUTH_CACHE_TTL = 300
_AUTH_CACHE_PREFIX = "auth:org:"


def _hash_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _cache_key(key_hash: str) -> str:
    return f"{_AUTH_CACHE_PREFIX}{key_hash}"


def _get_from_cache(key_hash: str) -> dict | None:
    try:
        redis = get_redis_client()
        raw = redis.get(_cache_key(key_hash))
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


def _set_cache(key_hash: str, org: dict) -> None:
    try:
        redis = get_redis_client()
        redis.setex(_cache_key(key_hash), _AUTH_CACHE_TTL, json.dumps(org, default=str))
    except Exception:
        pass


def _invalidate_cache(key_hash: str) -> None:
    """Invalida el cache de una API key (usar al revocar)."""
    try:
        redis = get_redis_client()
        redis.delete(_cache_key(key_hash))
    except Exception:
        pass


def get_current_org(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> OrgContext:
    """
    Dependency de FastAPI. Valida X-API-Key y retorna el contexto de organización.
    Lanza 401 si la clave falta, es inválida, está revocada o la org está suspendida.
    """
    if not x_api_key:
        _audit_auth_fail(request, None, "missing_api_key")
        raise HTTPException(
            status_code=401,
            detail="Se requiere el header X-API-Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    key_hash = _hash_key(x_api_key)

    # 1. Intentar cache Redis
    org = _get_from_cache(key_hash)

    # 2. Si no está en cache, consultar MySQL
    if org is None:
        org = get_org_by_key_hash(key_hash)
        if org:
            _set_cache(key_hash, org)
            # Actualizar last_used_at en background (no bloquea el request)
            try:
                update_key_last_used(org["api_key_id"])
            except Exception:
                pass

    if org is None:
        _audit_auth_fail(request, None, "invalid_api_key")
        raise HTTPException(
            status_code=401,
            detail="API key inválida o inactiva",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Enriquecer contexto con datos del request para auditoría
    org["_request_ip"] = _get_client_ip(request)
    org["_user_agent"] = request.headers.get("user-agent", "")[:256]

    return org


def require_master_key_or_admin(
    x_master_key: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """
    Dependency para endpoints de gestión de organizaciones.
    Acepta X-Master-Key (superusuario global) O un X-API-Key con is_admin=True.
    """
    # Intentar con Master Key primero
    if x_master_key and settings.MASTER_KEY and x_master_key == settings.MASTER_KEY:
        return
    # Intentar con Admin API Key
    if x_api_key:
        key_hash = _hash_key(x_api_key)
        org = _get_from_cache(key_hash)
        if org is None:
            org = get_org_by_key_hash(key_hash)
        if org and org.get("is_admin"):
            return
    raise HTTPException(
        status_code=401,
        detail="Se requiere X-Master-Key o un API key con permisos de administrador",
    )


def require_master_key(
    x_master_key: Annotated[str | None, Header()] = None,
) -> None:
    """
    Dependency para endpoints de administración (crear organizaciones).
    Valida X-Master-Key contra MASTER_KEY en config.
    """
    if not settings.MASTER_KEY:
        raise HTTPException(
            status_code=503,
            detail="MASTER_KEY no configurada en el servidor"
        )
    if not x_master_key or x_master_key != settings.MASTER_KEY:
        raise HTTPException(
            status_code=401,
            detail="X-Master-Key inválida o ausente"
        )


def log_audit(org: OrgContext, entity_type: str, action: str,
              entity_id: str | None = None, meta: dict | None = None) -> None:
    """
    Registra una operación en audit_log. Llamar desde los routers tras
    operaciones sensibles (create/update/delete de agentes, docs, etc.).
    """
    write_audit_log(
        entity_type=entity_type,
        action=action,
        org_id=org.get("org_id"),
        api_key_id=org.get("api_key_id"),
        entity_id=entity_id,
        ip_address=org.get("_request_ip"),
        user_agent=org.get("_user_agent"),
        meta=meta,
    )


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _audit_auth_fail(request: Request, org_id: int | None, reason: str) -> None:
    write_audit_log(
        entity_type="auth",
        action="auth_fail",
        org_id=org_id,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:256],
        meta={"reason": reason},
    )


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return ""


def invalidate_org_cache(key_hash: str) -> None:
    """Expone invalidación de cache para usar al revocar API keys."""
    _invalidate_cache(key_hash)
