"""
Router de WhatsApp.

Endpoints para vincular sesiones WA a organizaciones,
registrar números → agentes, y recibir mensajes via webhook.
"""

import re
from fastapi import APIRouter, HTTPException, Request
from ..config import settings
from ..schemas import (
    WhatsAppLinkRequest,
    WhatsAppNumberRegister,
    WhatsAppNumberBulkRegister,
    WhatsAppUpdateDefaultAgent,
    WhatsAppWebhookRegister,
    WhatsAppSendRequest,
    ChatRequest,
)
from ..agents import get_agent, agent_exists
from ..whatsapp import (
    link_session, get_org_config, get_org_by_session, unlink_session,
    update_default_agent, list_whatsapp_orgs, register_number,
    unregister_number, list_numbers, resolve_agent, save_webhook_url,
)
from ..whatsapp_client import (
    wa_create_session, wa_list_sessions, wa_get_qr, wa_delete_session,
    wa_register_webhook, wa_get_webhook, wa_delete_webhook,
    wa_send_message, wa_send_file, wa_list_contacts, wa_status,
)
from .chat import chat as chat_endpoint

router = APIRouter(prefix="/whatsapp", tags=["📱 WhatsApp"])


def normalize_session_id(text: str) -> str:
    """Convierte texto a ID alfanumérico puro + sufijo 'whts'.

    Ejemplo: 'Mi Agente-1' → 'miagente1whts'
    """
    clean = re.sub(r"[^a-zA-Z0-9]", "", text).lower()
    if not clean:
        clean = "session"
    if not clean.endswith("whts"):
        clean += "whts"
    return clean


# ── Vinculación organización ↔ sesión WA ─────────────────

@router.post("/link", summary="Vincular WhatsApp a una organización")
async def link_whatsapp(req: WhatsAppLinkRequest):
    """Crea una sesión de WhatsApp y la vincula a una organización.

    Si wa_session_id se omite, se genera automáticamente desde el nombre
    de la organización (solo alfanumérico + sufijo 'whts').

    Si se proporciona webhook_base_url, registra automáticamente el webhook
    para recibir mensajes entrantes.
    """
    # Validar que el agente default existe
    if not agent_exists(req.default_agent_id):
        raise HTTPException(
            status_code=400,
            detail=f"El agente por defecto '{req.default_agent_id}' no existe"
        )

    # Generar o normalizar session_id
    wa_session_id = normalize_session_id(req.wa_session_id or req.organization)

    # Verificar si la organización ya tiene WA vinculado
    existing = get_org_config(req.organization)
    if existing:
        if not req.force:
            raise HTTPException(
                status_code=400,
                detail=f"La organización '{req.organization}' ya tiene WhatsApp vinculado (sesión: {existing['wa_session_id']}). "
                       f"Use force=true para re-vincular, o desvincule primero con DELETE /whatsapp/link/{req.organization}"
            )
        # force=True: limpiar vinculación anterior
        old_session_id = existing.get("wa_session_id")
        if old_session_id:
            try:
                await wa_delete_webhook(old_session_id)
            except Exception:
                pass
            try:
                await wa_delete_session(old_session_id)
            except Exception:
                pass
        unlink_session(req.organization)

    # Limpiar sesión previa con el mismo ID en la API WA (evita QR stale)
    try:
        await wa_delete_session(wa_session_id)
    except Exception:
        pass  # No existía, está bien

    # Crear sesión en la API de WhatsApp
    try:
        wa_result = await wa_create_session(wa_session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error creando sesión en API WhatsApp: {str(e)}")

    # Guardar vinculación en Redis
    config = link_session(req.organization, wa_session_id, req.default_agent_id)

    # Registrar webhook automáticamente (usa webhook_base_url o PUBLIC_API_URL)
    webhook_registered = False
    base_url = (req.webhook_base_url or settings.PUBLIC_API_URL).rstrip("/")
    webhook_url = f"{base_url}/whatsapp/webhook/{wa_session_id}"
    try:
        await wa_register_webhook(wa_session_id, webhook_url)
        webhook_registered = True
        save_webhook_url(req.organization, webhook_url)
        config["webhook_url"] = webhook_url
    except Exception as e:
        config["webhook_warning"] = f"Sesión creada pero webhook falló: {str(e)}"
        config["webhook_url"] = webhook_url

    return {
        "status": "ok",
        "message": f"WhatsApp vinculado a organización '{req.organization}'",
        "config": config,
        "wa_session": wa_result,
        "webhook_registered": webhook_registered,
    }


@router.delete("/link/{organization}", summary="Desvincular WhatsApp de una organización")
async def unlink_whatsapp(organization: str):
    """Desvincula WhatsApp de una organización: elimina sesión WA, webhook y registros."""
    config = get_org_config(organization)
    if not config:
        raise HTTPException(status_code=404, detail=f"La organización '{organization}' no tiene WhatsApp vinculado")

    wa_session_id = config["wa_session_id"]

    # Intentar eliminar webhook y sesión en la API de WA
    errors = []
    try:
        await wa_delete_webhook(wa_session_id)
    except Exception:
        pass  # El webhook puede no existir

    try:
        await wa_delete_session(wa_session_id)
    except Exception as e:
        errors.append(f"Error eliminando sesión WA: {str(e)}")

    # Limpiar datos en Redis
    unlink_session(organization)

    result = {
        "status": "ok",
        "message": f"WhatsApp desvinculado de '{organization}'",
    }
    if errors:
        result["warnings"] = errors

    return result


@router.get("/link", summary="Listar organizaciones con WhatsApp")
async def list_linked_orgs():
    """Lista todas las organizaciones que tienen WhatsApp vinculado."""
    orgs = list_whatsapp_orgs()
    return {"organizations": orgs, "count": len(orgs)}


@router.get("/link/{organization}", summary="Ver config WhatsApp de una organización")
async def get_org_whatsapp(organization: str):
    """Obtiene la configuración WhatsApp de una organización, incluyendo números registrados
    y estado del webhook.

    Si la organización no tiene WhatsApp vinculado, retorna linked=false
    en vez de 404, para que el frontend pueda distinguir el estado.

    Incluye automáticamente:
    - **webhook_url**: URL esperada del webhook (construida desde PUBLIC_API_URL)
    - **webhook_registered**: si el webhook está registrado en la API de WhatsApp
    """
    config = get_org_config(organization)
    if not config:
        return {
            "linked": False,
            "organization": organization,
            "registered_numbers": [],
            "registered_count": 0,
            "webhook": {
                "url": "",
                "registered": False,
            },
        }

    config["linked"] = True
    numbers = list_numbers(organization)
    config["registered_numbers"] = numbers
    config["registered_count"] = len(numbers)

    # Construir URL del webhook automáticamente
    wa_session_id = config.get("wa_session_id", "")
    base_url = settings.PUBLIC_API_URL.rstrip("/")
    expected_webhook_url = f"{base_url}/whatsapp/webhook/{wa_session_id}"
    saved_webhook_url = config.get("webhook_url", "")

    # Verificar estado real en la API de WhatsApp
    wa_webhook_active = False
    try:
        wa_webhook = await wa_get_webhook(wa_session_id)
        wa_webhook_active = bool(wa_webhook)
    except Exception:
        pass

    config["webhook"] = {
        "url": saved_webhook_url or expected_webhook_url,
        "expected_url": expected_webhook_url,
        "registered": wa_webhook_active and bool(saved_webhook_url),
    }

    return config


@router.put("/link/{organization}/default-agent", summary="Cambiar agente por defecto")
async def change_default_agent(organization: str, req: WhatsAppUpdateDefaultAgent):
    """Cambia el agente que atiende números no registrados."""
    if not agent_exists(req.default_agent_id):
        raise HTTPException(status_code=400, detail=f"El agente '{req.default_agent_id}' no existe")

    try:
        config = update_default_agent(organization, req.default_agent_id)
        return config
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/link/{organization}/webhook", summary="Registrar webhook de una organización")
async def register_org_webhook(organization: str, req: WhatsAppWebhookRegister | None = None):
    """Registra el webhook para recibir mensajes entrantes de WhatsApp.

    Construye automáticamente la URL completa del webhook:
    {PUBLIC_API_URL}/whatsapp/webhook/{wa_session_id}

    Se puede llamar sin body (usa PUBLIC_API_URL del .env) o con body
    para especificar una URL base diferente.

    Si ya existía un webhook registrado, lo reemplaza.
    """
    config = get_org_config(organization)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"La organización '{organization}' no tiene WhatsApp vinculado"
        )

    wa_session_id = config["wa_session_id"]
    base_url = ((req.webhook_base_url if req else None) or settings.PUBLIC_API_URL).rstrip("/")
    webhook_url = f"{base_url}/whatsapp/webhook/{wa_session_id}"

    # Eliminar webhook anterior si existe
    try:
        await wa_delete_webhook(wa_session_id)
    except Exception:
        pass

    # Registrar nuevo webhook en la API de WhatsApp
    try:
        wa_result = await wa_register_webhook(wa_session_id, webhook_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error registrando webhook en API WhatsApp: {str(e)}")

    # Persistir en Redis para re-registro automático al reiniciar
    save_webhook_url(organization, webhook_url)

    return {
        "status": "ok",
        "organization": organization,
        "wa_session_id": wa_session_id,
        "webhook_url": webhook_url,
        "wa_response": wa_result,
    }


@router.delete("/link/{organization}/webhook", summary="Eliminar webhook de una organización")
async def delete_org_webhook(organization: str):
    """Elimina el webhook de una organización."""
    config = get_org_config(organization)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"La organización '{organization}' no tiene WhatsApp vinculado"
        )

    wa_session_id = config["wa_session_id"]

    try:
        await wa_delete_webhook(wa_session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error eliminando webhook: {str(e)}")

    # Limpiar webhook_url de Redis
    save_webhook_url(organization, "")

    return {
        "status": "ok",
        "message": f"Webhook eliminado de '{organization}'",
    }


@router.get("/link/{organization}/webhook", summary="Ver webhook de una organización")
async def get_org_webhook(organization: str):
    """Obtiene el webhook registrado de una organización."""
    config = get_org_config(organization)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"La organización '{organization}' no tiene WhatsApp vinculado"
        )

    wa_session_id = config["wa_session_id"]
    webhook_url = config.get("webhook_url", "")

    # Verificar estado real en la API de WhatsApp
    wa_webhook = None
    try:
        wa_webhook = await wa_get_webhook(wa_session_id)
    except Exception:
        pass

    return {
        "organization": organization,
        "wa_session_id": wa_session_id,
        "webhook_url": webhook_url,
        "registered": bool(webhook_url),
        "wa_status": wa_webhook,
    }


# ── Registro de números ──────────────────────────────────

@router.post("/numbers/{organization}", summary="Registrar número → agente")
async def register_phone_number(organization: str, req: WhatsAppNumberRegister):
    """Registra un número telefónico para que sea atendido por un agente específico.

    El número se normaliza automáticamente (solo dígitos) para garantizar
    que coincida con el formato de los mensajes entrantes del webhook.
    """
    if not agent_exists(req.agent_id):
        raise HTTPException(status_code=400, detail=f"El agente '{req.agent_id}' no existe")

    phone = _normalize_phone(req.phone_number)
    if not phone:
        raise HTTPException(status_code=400, detail="Número telefónico inválido")

    try:
        result = register_number(organization, phone, req.agent_id)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/numbers/{organization}/bulk", summary="Registrar múltiples números")
async def register_phone_numbers_bulk(organization: str, req: WhatsAppNumberBulkRegister):
    """Registra múltiples números telefónicos a la vez."""
    results = []
    errors = []

    for entry in req.numbers:
        if not agent_exists(entry.agent_id):
            errors.append({"phone_number": entry.phone_number, "error": f"Agente '{entry.agent_id}' no existe"})
            continue
        phone = _normalize_phone(entry.phone_number)
        if not phone:
            errors.append({"phone_number": entry.phone_number, "error": "Número telefónico inválido"})
            continue
        try:
            result = register_number(organization, phone, entry.agent_id)
            results.append(result)
        except ValueError as e:
            errors.append({"phone_number": entry.phone_number, "error": str(e)})

    return {
        "registered": results,
        "errors": errors,
        "registered_count": len(results),
        "error_count": len(errors),
    }


@router.get("/numbers/{organization}", summary="Listar números registrados")
async def list_phone_numbers(organization: str):
    """Lista todos los números registrados de una organización con su agente asignado."""
    config = get_org_config(organization)
    if not config:
        raise HTTPException(status_code=404, detail=f"La organización '{organization}' no tiene WhatsApp vinculado")

    numbers = list_numbers(organization)
    return {
        "organization": organization,
        "default_agent_id": config.get("default_agent_id", "default"),
        "numbers": numbers,
        "count": len(numbers),
    }


@router.delete("/numbers/{organization}/{phone_number}", summary="Eliminar registro de número")
async def unregister_phone_number(organization: str, phone_number: str):
    """Elimina el registro de un número. Los mensajes de este número irán al agente por defecto."""
    phone_number = _normalize_phone(phone_number)
    success = unregister_number(organization, phone_number)
    if not success:
        raise HTTPException(status_code=404, detail=f"Número '{phone_number}' no registrado en '{organization}'")

    return {"status": "ok", "message": f"Número '{phone_number}' eliminado de '{organization}'"}


# ── Webhook (recibe mensajes entrantes) ──────────────────

def _normalize_phone(raw: str) -> str:
    """Normaliza un número de teléfono: quita @s.whatsapp.net, @c.us, +, espacios, guiones."""
    phone = raw.split("@")[0]  # quitar @s.whatsapp.net o @c.us
    phone = re.sub(r"[^\d]", "", phone)  # solo dígitos
    return phone


@router.post("/webhook/{wa_session_id}", summary="Webhook para mensajes entrantes")
async def webhook_receive(wa_session_id: str, request: Request):
    """Recibe mensajes de WhatsApp, los rutea al agente correspondiente y responde.

    El flujo es:
    1. Resolver organización por session_id
    2. Normalizar número del remitente
    3. Buscar agente asignado al número (o usar el default)
    4. Enviar mensaje al chat del agente
    5. Responder por WhatsApp con la respuesta del agente
    """
    body = await request.json()

    # Extraer datos del mensaje entrante
    # Formato típico: {from: "5215512345678@s.whatsapp.net", body: "Hola", ...}
    # Formato LID:    {from: "186878456262709@lid", name: "@ndres", body: "Hola", ...}
    sender_raw = body.get("from", "")
    sender_name = body.get("name", "")
    message_text = body.get("body", "") or body.get("text", "") or body.get("message", "")

    if not sender_raw or not message_text:
        return {"status": "ignored", "reason": "Mensaje sin remitente o texto vacío"}

    # Resolver número real del remitente
    # WhatsApp puede enviar LIDs (Linked IDs) en vez de números telefónicos.
    # En ese caso, buscamos el contacto por nombre para obtener el número real.
    sender_phone = _normalize_phone(sender_raw)
    is_lid = sender_raw.endswith("@lid")

    if is_lid and sender_name:
        try:
            result = await wa_list_contacts(wa_session_id, sender_name)
            contacts = result.get("contacts", []) if isinstance(result, dict) else result
            for contact in contacts:
                if contact.get("name") == sender_name and contact.get("number"):
                    sender_phone = contact["number"]
                    break
        except Exception:
            pass  # Si falla el lookup, continuamos con el LID normalizado

    # Resolver agente
    organization, agent_id, routing_type = resolve_agent(wa_session_id, sender_phone)
    if not organization:
        return {"status": "ignored", "reason": f"Sesión '{wa_session_id}' no vinculada a ninguna organización"}

    # Verificar que el agente existe
    agent = get_agent(agent_id)
    if not agent:
        agent_id = "default"
        routing_type = "fallback"

    # Construir request de chat usando el número como session_id (mantiene contexto por conversación)
    chat_session_id = f"wa_{sender_phone}"
    chat_req = ChatRequest(
        message=message_text,
        agent_id=agent_id,
        session_id=chat_session_id,
    )

    # Ejecutar chat
    try:
        chat_response = await chat_endpoint(chat_req)
    except Exception as e:
        # Intentar notificar error por WA
        error_msg = "Lo siento, ocurrió un error procesando tu mensaje. Intenta de nuevo."
        try:
            await wa_send_message(wa_session_id, sender_phone, error_msg)
        except Exception:
            pass
        return {"status": "error", "detail": str(e)}

    # Extraer respuesta del agente
    assistant_reply = chat_response.get("answer", "") or chat_response.get("response", "")

    # Enviar respuesta por WhatsApp
    try:
        await wa_send_message(wa_session_id, sender_phone, assistant_reply)
    except Exception as e:
        return {
            "status": "error",
            "detail": f"Chat procesado pero falló envío WA: {str(e)}",
            "agent_response": assistant_reply,
        }

    return {
        "status": "ok",
        "organization": organization,
        "agent_id": agent_id,
        "routing_type": routing_type,
        "sender": sender_phone,
        "response_length": len(assistant_reply),
    }


# ── Proxy a la API de WhatsApp (sesiones, QR, contactos) ─

@router.get("/sessions", summary="Listar sesiones WA activas")
async def list_wa_sessions():
    """Proxy: lista sesiones activas en la API de WhatsApp."""
    try:
        return await wa_list_sessions()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error consultando API WhatsApp: {str(e)}")


@router.get("/sessions/{wa_session_id}/qr", summary="Obtener código QR")
async def get_wa_qr(wa_session_id: str):
    """Proxy: obtiene el código QR para vincular un dispositivo."""
    try:
        return await wa_get_qr(wa_session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error obteniendo QR: {str(e)}")


@router.get("/sessions/{wa_session_id}/contacts", summary="Listar contactos")
async def list_wa_contacts(wa_session_id: str, q: str = ""):
    """Proxy: lista contactos de una sesión de WhatsApp."""
    try:
        return await wa_list_contacts(wa_session_id, q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error listando contactos: {str(e)}")


# ── Webhook management ───────────────────────────────────

@router.post("/sessions/{wa_session_id}/webhook", summary="Registrar webhook manualmente")
async def register_wa_webhook(wa_session_id: str, webhook_url: str):
    """Registra un webhook en la API de WhatsApp y lo persiste para re-registro al reiniciar."""
    try:
        result = await wa_register_webhook(wa_session_id, webhook_url)
        # Persistir en Redis para re-registro automático al reiniciar
        org = get_org_by_session(wa_session_id)
        if org:
            save_webhook_url(org, webhook_url)
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error registrando webhook: {str(e)}")


@router.get("/sessions/{wa_session_id}/webhook", summary="Ver webhook registrado")
async def get_wa_webhook(wa_session_id: str):
    """Obtiene el webhook registrado de una sesión."""
    try:
        return await wa_get_webhook(wa_session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error consultando webhook: {str(e)}")


@router.delete("/sessions/{wa_session_id}/webhook", summary="Eliminar webhook")
async def delete_wa_webhook(wa_session_id: str):
    """Elimina el webhook de una sesión."""
    try:
        return await wa_delete_webhook(wa_session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error eliminando webhook: {str(e)}")


# ── Envío manual de mensajes ─────────────────────────────

@router.post("/send", summary="Enviar mensaje manual por WhatsApp")
async def send_wa_message(req: WhatsAppSendRequest):
    """Envía un mensaje de texto por WhatsApp usando la sesión vinculada a la organización."""
    config = get_org_config(req.organization)
    if not config:
        raise HTTPException(status_code=404, detail=f"La organización '{req.organization}' no tiene WhatsApp vinculado")

    try:
        result = await wa_send_message(config["wa_session_id"], req.to, req.text)
        return {"status": "ok", "wa_response": result}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error enviando mensaje: {str(e)}")


# ── Estado global ─────────────────────────────────────────

@router.get("/status", summary="Estado de WhatsApp")
async def whatsapp_status():
    """Estado global: sesiones de la API WA + organizaciones vinculadas."""
    try:
        wa_stat = await wa_status()
    except Exception:
        wa_stat = {"error": "API WhatsApp no disponible"}

    orgs = list_whatsapp_orgs()
    return {
        "whatsapp_api": wa_stat,
        "linked_organizations": orgs,
        "linked_count": len(orgs),
    }
