"""
Cliente HTTP para la API de WhatsApp (localhost:3001).

Gestiona sesiones, webhooks y envío de mensajes.
"""

import os
import httpx
from .config import settings

WHATSAPP_API_URL = os.getenv("WHATSAPP_API_URL", "http://localhost:3001")

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=WHATSAPP_API_URL, timeout=30.0)
    return _client


# ── Sesiones ──────────────────────────────────────────────

async def wa_create_session(session_id: str) -> dict:
    """Crea una nueva sesión de WhatsApp."""
    client = _get_client()
    resp = await client.post("/sessions", json={"id": session_id})
    resp.raise_for_status()
    return resp.json()


async def wa_list_sessions() -> list:
    """Lista sesiones activas."""
    client = _get_client()
    resp = await client.get("/sessions")
    resp.raise_for_status()
    return resp.json()


async def wa_get_qr(session_id: str) -> dict:
    """Obtiene el código QR para vincular un dispositivo."""
    client = _get_client()
    resp = await client.get(f"/sessions/{session_id}/qr")
    resp.raise_for_status()
    return resp.json()


async def wa_delete_session(session_id: str) -> dict:
    """Elimina una sesión de WhatsApp."""
    client = _get_client()
    resp = await client.delete(f"/sessions/{session_id}")
    resp.raise_for_status()
    return resp.json()


# ── Webhooks ──────────────────────────────────────────────

async def wa_register_webhook(session_id: str, webhook_url: str) -> dict:
    """Registra un webhook para recibir mensajes entrantes."""
    client = _get_client()
    resp = await client.post(
        f"/sessions/{session_id}/webhook",
        json={"url": webhook_url}
    )
    resp.raise_for_status()
    return resp.json()


async def wa_get_webhook(session_id: str) -> dict:
    """Obtiene el webhook registrado de una sesión."""
    client = _get_client()
    resp = await client.get(f"/sessions/{session_id}/webhook")
    resp.raise_for_status()
    return resp.json()


async def wa_delete_webhook(session_id: str) -> dict:
    """Elimina el webhook de una sesión."""
    client = _get_client()
    resp = await client.delete(f"/sessions/{session_id}/webhook")
    resp.raise_for_status()
    return resp.json()


# ── Mensajes ──────────────────────────────────────────────

async def wa_send_message(session_id: str, to: str, text: str) -> dict:
    """Envía un mensaje de texto por WhatsApp."""
    client = _get_client()
    resp = await client.post(
        f"/sessions/{session_id}/send",
        json={"to": to, "message": text}
    )
    resp.raise_for_status()
    return resp.json()


async def wa_send_file(session_id: str, to: str, file_url: str, caption: str = "") -> dict:
    """Envía un archivo por WhatsApp."""
    client = _get_client()
    payload = {"to": to, "url": file_url}
    if caption:
        payload["caption"] = caption
    resp = await client.post(
        f"/sessions/{session_id}/send-file",
        json=payload
    )
    resp.raise_for_status()
    return resp.json()


# ── Contactos ─────────────────────────────────────────────

async def wa_list_contacts(session_id: str, query: str = "") -> list:
    """Lista contactos de una sesión."""
    client = _get_client()
    params = {"q": query} if query else {}
    resp = await client.get(f"/sessions/{session_id}/contacts", params=params)
    resp.raise_for_status()
    return resp.json()


# ── Estado ────────────────────────────────────────────────

async def wa_status() -> dict:
    """Estado global de todas las sesiones de WhatsApp."""
    client = _get_client()
    resp = await client.get("/status")
    resp.raise_for_status()
    return resp.json()
