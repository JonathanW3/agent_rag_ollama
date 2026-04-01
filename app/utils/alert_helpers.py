"""
Helpers para enviar alertas internas (WhatsApp + Email) cuando se agenda
una reunión o se genera una cotización.

El mismo texto plano se envía por ambos canales.
"""

import asyncio
from datetime import datetime
from typing import Any


def build_calendar_alert(
    calendar_result: dict,
    calendar_action: dict,
    session_id: str,
    agent_name: str,
    conversation_summary: list[dict],
) -> str:
    """Construye el texto de alerta para una reunión agendada."""
    summary = calendar_action.get("summary", "Sin título")
    start = calendar_action.get("start_datetime", "—")
    end = calendar_action.get("end_datetime", "—")
    location = calendar_action.get("location", "No especificada")
    description = calendar_action.get("description", "")
    attendees = calendar_action.get("attendees") or []
    meet_link = calendar_result.get("meet_link", "")
    event_id = calendar_result.get("event_id", "")

    lines = [
        "🗓️ *ALERTA: REUNIÓN AGENDADA*",
        "",
        f"*Evento:* {summary}",
        f"*Inicio:* {start}",
        f"*Fin:* {end}",
        f"*Ubicación:* {location}",
    ]
    if attendees:
        lines.append(f"*Participantes:* {', '.join(attendees)}")
    if meet_link:
        lines.append(f"*Google Meet:* {meet_link}")
    if description:
        lines.append(f"*Descripción:* {description}")
    lines.append(f"*Event ID:* {event_id}")
    lines.append("")
    lines.append(f"*Agente:* {agent_name}")
    lines.append(f"*Sesión:* {session_id}")

    # Resumen de conversación (últimos mensajes)
    lines.append("")
    lines.append("📋 *Resumen de conversación:*")
    lines.extend(_format_conversation(conversation_summary))

    return "\n".join(lines)


def build_cotizacion_alert(
    cotizacion_action: dict,
    session_id: str,
    agent_name: str,
    conversation_summary: list[dict],
) -> str:
    """Construye el texto de alerta para una cotización solicitada."""
    cliente = cotizacion_action.get("cliente", "No identificado")
    productos = cotizacion_action.get("productos", [])
    total = cotizacion_action.get("total", "—")
    notas = cotizacion_action.get("notas", "")
    moneda = cotizacion_action.get("moneda", "USD")

    lines = [
        "💰 *ALERTA: COTIZACIÓN SOLICITADA*",
        "",
        f"*Cliente:* {cliente}",
    ]

    if productos:
        lines.append("*Productos/Servicios:*")
        for p in productos:
            if isinstance(p, dict):
                nombre = p.get("nombre", p.get("producto", "—"))
                cantidad = p.get("cantidad", 1)
                precio = p.get("precio", "—")
                lines.append(f"  • {nombre} x{cantidad} — {precio}")
            else:
                lines.append(f"  • {p}")

    lines.append(f"*Total:* {total} {moneda}")
    if notas:
        lines.append(f"*Notas:* {notas}")

    lines.append("")
    lines.append(f"*Agente:* {agent_name}")
    lines.append(f"*Sesión:* {session_id}")

    # Resumen de conversación
    lines.append("")
    lines.append("📋 *Resumen de conversación:*")
    lines.extend(_format_conversation(conversation_summary))

    return "\n".join(lines)


def _format_conversation(messages: list[dict], max_messages: int = 10) -> list[str]:
    """Formatea los últimos mensajes de la conversación para la alerta."""
    recent = messages[-max_messages:] if len(messages) > max_messages else messages
    lines = []
    for msg in recent:
        role = "👤 Usuario" if msg.get("role") == "user" else "🤖 Asistente"
        content = msg.get("content", "")
        # Truncar mensajes largos
        if len(content) > 300:
            content = content[:300] + "..."
        # Limpiar bloques de acción del contenido
        import re
        content = re.sub(r'\[(EMAIL|CALENDAR|CHART|COTIZACION)_ACTION\].*?\[/\1_ACTION\]', '', content, flags=re.DOTALL).strip()
        content = re.sub(r'\[RESULTADO DE.*?\].*?\[/RESULTADO DE.*?\]', '', content, flags=re.DOTALL).strip()
        if content:
            lines.append(f"{role}: {content}")
    return lines


async def send_alert(
    alert_text: str,
    alert_wa_session_id: str | None,
    alert_wa_number: str | None,
    alert_email: str | None,
    smtp_config: dict | None,
    agent_name: str = "Asistente IA",
) -> dict[str, Any]:
    """Envía la alerta por WhatsApp y/o Email en paralelo.

    Returns:
        Dict con resultados de cada canal.
    """
    results: dict[str, Any] = {"whatsapp": None, "email": None}
    tasks = []

    # WhatsApp
    if alert_wa_session_id and alert_wa_number:
        tasks.append(_send_wa_alert(alert_wa_session_id, alert_wa_number, alert_text, results))

    # Email
    if alert_email and smtp_config:
        tasks.append(_send_email_alert(alert_email, alert_text, smtp_config, agent_name, results))

    if tasks:
        await asyncio.gather(*tasks)

    return results


async def _send_wa_alert(
    session_id: str,
    number: str,
    text: str,
    results: dict,
) -> None:
    """Envía alerta por WhatsApp."""
    try:
        from ..whatsapp_client import wa_send_message
        resp = await wa_send_message(session_id, number, text)
        results["whatsapp"] = {"success": True, "response": resp}
        print(f"[ALERT] WhatsApp enviado a {number}")
    except Exception as e:
        results["whatsapp"] = {"success": False, "error": str(e)}
        print(f"[ALERT] Error WhatsApp: {e}")


async def _send_email_alert(
    to_email: str,
    text: str,
    smtp_config: dict,
    agent_name: str,
    results: dict,
) -> None:
    """Envía alerta por Email con el mismo texto."""
    try:
        from mcp_email.client import get_email_client
        from .email_helpers import wrap_email_template

        # Determinar asunto según tipo de alerta
        if "REUNIÓN AGENDADA" in text:
            subject = "Alerta: Nueva reunión agendada"
        elif "COTIZACIÓN SOLICITADA" in text:
            subject = "Alerta: Nueva cotización solicitada"
        else:
            subject = "Alerta del sistema"

        # Convertir texto plano a HTML básico (reemplazar saltos de línea)
        html_body = text.replace("*", "<b>").replace("\n", "<br>\n")
        # Cerrar negritas abiertas: transformar pares <b>...<b> en <b>...</b>
        import re
        html_body = re.sub(r'<b>(.*?)<b>', r'<b>\1</b>', html_body)

        wrapped = wrap_email_template(
            body=html_body,
            subject=subject,
            is_html=True,
            agent_name=agent_name,
            sender_email=smtp_config.get("email", ""),
        )

        email_client = get_email_client()
        resp = await email_client.send_email(
            smtp_config=smtp_config,
            to=to_email,
            subject=subject,
            body=wrapped,
            html=True,
        )
        results["email"] = {"success": resp.get("success", False), "message": resp.get("message", "")}
        print(f"[ALERT] Email enviado a {to_email}")
    except Exception as e:
        results["email"] = {"success": False, "error": str(e)}
        print(f"[ALERT] Error Email: {e}")
