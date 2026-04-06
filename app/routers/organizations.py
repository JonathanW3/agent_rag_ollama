"""
Endpoints de gestión de organizaciones y API keys.

POST   /organizations                          → Crear organización (requiere X-Master-Key)
GET    /organizations                          → Listar organizaciones (requiere X-Master-Key)
GET    /organizations/{company_lic_cod}        → Detalle de organización (requiere X-Master-Key)
PATCH  /organizations/{company_lic_cod}/status → Activar/suspender (requiere X-Master-Key)
GET    /organizations/me                       → Info de la org del token actual
POST   /organizations/{company_lic_cod}/keys  → Agregar API key (requiere X-Master-Key)
DELETE /organizations/keys/{api_key_id}        → Revocar API key (requiere X-Master-Key)
POST   /organizations/keys/{api_key_id}/rotate → Rotar API key (requiere X-Master-Key)
"""

import hashlib
import secrets
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..auth import get_current_org, require_master_key, require_master_key_or_admin, OrgContext, invalidate_org_cache
from ..db_platform import (
    create_organization, get_organization, list_organizations as db_list_orgs,
    set_organization_active, create_api_key, list_api_keys, revoke_api_key, rotate_api_key
)

router = APIRouter(prefix="/organizations", tags=["🏢 Organizaciones"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class OrgCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=128,
                      description="Nombre comercial de la organización")
    company_lic_cod: str = Field(..., min_length=2, max_length=32,
                                  pattern=r"^[A-Z0-9][A-Z0-9\-_]{1,31}$",
                                  description="Código único legible. Solo mayúsculas, números, guiones. Ej: FARMA-001")
    label: str = Field(default="default", max_length=64,
                       description="Etiqueta para la primera API key")


class OrgStatusUpdate(BaseModel):
    is_active: bool


class ApiKeyCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=64,
                       description="Etiqueta descriptiva. Ej: produccion, dev, whatsapp")


class ApiKeyRotate(BaseModel):
    label: str = Field(default="rotada", max_length=64,
                       description="Etiqueta para la nueva clave")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_key_pair() -> tuple[str, str]:
    """Genera (api_key, key_hash). La key tiene prefijo 'rag_' para identificación."""
    raw = secrets.token_urlsafe(48)
    api_key = f"rag_{raw}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return api_key, key_hash


def _org_not_found(company_lic_cod: str):
    raise HTTPException(
        status_code=404,
        detail=f"Organización '{company_lic_cod}' no encontrada"
    )


# ---------------------------------------------------------------------------
# Endpoints de administración (requieren X-Master-Key)
# ---------------------------------------------------------------------------

@router.post("", summary="Crear organización",
             dependencies=[Depends(require_master_key_or_admin)])
def create_org(req: OrgCreate):
    """
    Crea una organización nueva y genera su primera API key.
    El secreto **solo se retorna en esta respuesta** — no se puede recuperar después.
    Requiere header: X-Master-Key
    """
    # Verificar que el código no existe
    existing = get_organization(req.company_lic_cod)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"El código '{req.company_lic_cod}' ya está en uso"
        )

    api_key, key_hash = _generate_key_pair()

    result = create_organization(
        name=req.name,
        company_lic_cod=req.company_lic_cod,
        api_key=api_key,
        key_hash=key_hash,
        label=req.label,
    )

    return {
        "org_id": result.get("org_id"),
        "company_lic_cod": req.company_lic_cod,
        "name": req.name,
        "api_key": api_key,          # ← único momento en que se expone el secreto
        "api_key_id": result.get("api_key_id"),
        "label": req.label,
        "warning": "Guarda esta API key de forma segura. No podrás volver a verla."
    }


@router.get("", summary="Listar organizaciones",
            dependencies=[Depends(require_master_key_or_admin)])
def list_orgs():
    """Lista todas las organizaciones registradas. Requiere X-Master-Key."""
    orgs = db_list_orgs()
    return {"organizations": orgs, "count": len(orgs)}


@router.get("/me", summary="Mi organización")
def get_my_org(org: OrgContext = Depends(get_current_org)):
    """Retorna la información de la organización asociada al API key del request."""
    return {
        "org_id": org["org_id"],
        "org_name": org["org_name"],
        "company_lic_cod": org["company_lic_cod"],
        "max_agents": org["max_agents"],
        "key_label": org["key_label"],
        "is_admin": bool(org.get("is_admin")),
    }


@router.get("/{company_lic_cod}", summary="Detalle de organización",
            dependencies=[Depends(require_master_key_or_admin)])
def get_org(company_lic_cod: str):
    """Obtiene el detalle de una organización. Requiere X-Master-Key."""
    org = get_organization(company_lic_cod)
    if not org:
        _org_not_found(company_lic_cod)
    return org


@router.patch("/{company_lic_cod}/status", summary="Activar o suspender organización",
              dependencies=[Depends(require_master_key_or_admin)])
def update_org_status(company_lic_cod: str, req: OrgStatusUpdate):
    """
    Activa (is_active=true) o suspende (is_active=false) una organización.
    Al suspender, todos sus API keys quedan inválidos de inmediato (Redis TTL).
    Requiere X-Master-Key.
    """
    org = get_organization(company_lic_cod)
    if not org:
        _org_not_found(company_lic_cod)

    set_organization_active(org["id"], req.is_active)

    return {
        "company_lic_cod": company_lic_cod,
        "is_active": req.is_active,
        "message": "Organización activada" if req.is_active else
                   "Organización suspendida. Los keys activos expirarán del cache en máx 5 min."
    }


# ---------------------------------------------------------------------------
# Endpoints de API keys (requieren X-Master-Key)
# ---------------------------------------------------------------------------

@router.get("/{company_lic_cod}/keys", summary="Listar API keys",
            dependencies=[Depends(require_master_key_or_admin)])
def get_org_keys(company_lic_cod: str):
    """
    Lista las API keys de una organización sin exponer el secreto.
    Requiere X-Master-Key.
    """
    org = get_organization(company_lic_cod)
    if not org:
        _org_not_found(company_lic_cod)

    keys = list_api_keys(org["id"])
    return {"company_lic_cod": company_lic_cod, "api_keys": keys, "count": len(keys)}


@router.post("/{company_lic_cod}/keys", summary="Agregar API key",
             dependencies=[Depends(require_master_key_or_admin)])
def add_api_key(company_lic_cod: str, req: ApiKeyCreate):
    """
    Genera una nueva API key para la organización.
    El secreto **solo se retorna en esta respuesta**.
    Requiere X-Master-Key.
    """
    org = get_organization(company_lic_cod)
    if not org:
        _org_not_found(company_lic_cod)

    api_key, key_hash = _generate_key_pair()
    result = create_api_key(
        org_id=org["id"],
        api_key=api_key,
        key_hash=key_hash,
        label=req.label,
    )

    return {
        "api_key_id": result["api_key_id"],
        "company_lic_cod": company_lic_cod,
        "label": req.label,
        "api_key": api_key,
        "warning": "Guarda esta API key de forma segura. No podrás volver a verla."
    }


@router.delete("/keys/{api_key_id}", summary="Revocar API key",
               dependencies=[Depends(require_master_key_or_admin)])
def revoke_key(api_key_id: int, company_lic_cod: str):
    """
    Revoca una API key específica. El cache Redis expirará en máx 5 min.
    Requiere X-Master-Key y el company_lic_cod de la organización dueña.
    """
    org = get_organization(company_lic_cod)
    if not org:
        _org_not_found(company_lic_cod)

    revoked = revoke_api_key(api_key_id=api_key_id, org_id=org["id"])
    if not revoked:
        raise HTTPException(
            status_code=404,
            detail=f"API key {api_key_id} no encontrada, ya revocada o no pertenece a '{company_lic_cod}'"
        )

    return {
        "api_key_id": api_key_id,
        "revoked": True,
        "note": "La clave quedará inválida en máx 5 min (TTL cache Redis)"
    }


@router.post("/keys/{api_key_id}/rotate", summary="Rotar API key",
             dependencies=[Depends(require_master_key_or_admin)])
def rotate_key(api_key_id: int, req: ApiKeyRotate):
    """
    Revoca la clave indicada y genera una nueva para la misma organización.
    El nuevo secreto **solo se retorna en esta respuesta**.
    Requiere X-Master-Key.
    """
    new_api_key, new_key_hash = _generate_key_pair()

    try:
        result = rotate_api_key(
            old_api_key_id=api_key_id,
            new_api_key=new_api_key,
            new_key_hash=new_key_hash,
            label=req.label,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "old_api_key_id": api_key_id,
        "new_api_key_id": result.get("new_api_key_id"),
        "org_id": result.get("org_id"),
        "api_key": new_api_key,
        "warning": "Guarda esta API key de forma segura. No podrás volver a verla."
    }
