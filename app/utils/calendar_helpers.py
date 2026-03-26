import re
import json
from .json_sanitize import sanitize_llm_json


def parse_calendar_actions(text: str) -> tuple[list[dict], str]:
    """Parsea bloques [CALENDAR_ACTION]{json}[/CALENDAR_ACTION] de la respuesta del LLM.

    Returns:
        Tupla de (lista de acciones calendar, texto limpio sin bloques).
    """
    pattern = r'\[CALENDAR_ACTION\](.*?)\[/CALENDAR_ACTION\]'
    actions: list[dict] = []

    for match in re.finditer(pattern, text, re.DOTALL):
        raw_json = match.group(1).strip()
        if not raw_json:
            actions.append({"_parse_error": "Bloque CALENDAR_ACTION vacío", "_raw": ""})
            continue
        sanitized = sanitize_llm_json(raw_json)
        if not sanitized.strip():
            actions.append({"_parse_error": "JSON vacío después de sanitizar", "_raw": raw_json})
            continue
        try:
            action = json.loads(sanitized)
            # Validar que tenga action_type
            if "action_type" not in action:
                actions.append({"_parse_error": "Falta campo 'action_type'", "_raw": raw_json})
            else:
                actions.append(action)
        except json.JSONDecodeError as e:
            actions.append({"_parse_error": f"JSON inválido: {e}", "_raw": raw_json})

    cleaned = re.sub(pattern, '', text, flags=re.DOTALL).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return actions, cleaned


async def execute_calendar_actions(
    actions: list[dict],
    calendar_client,
) -> list[dict]:
    """Ejecuta acciones de calendario usando el cliente MCP Google Calendar."""
    results: list[dict] = []

    for i, action in enumerate(actions):
        if "_parse_error" in action:
            results.append({"index": i, "success": False, "error": action["_parse_error"]})
            continue

        action_type = action.get("action_type")

        try:
            if action_type == "create_event":
                result = await calendar_client.create_event(
                    summary=action["summary"],
                    start_datetime=action["start_datetime"],
                    end_datetime=action["end_datetime"],
                    description=action.get("description", ""),
                    location=action.get("location", ""),
                    attendees=action.get("attendees"),
                    timezone=action.get("timezone", "America/Mexico_City"),
                    add_meet=action.get("add_meet", False),
                    calendar_id=action.get("calendar_id", "primary"),
                )
                results.append({
                    "index": i,
                    "action_type": action_type,
                    "summary": action.get("summary", ""),
                    "success": result.get("success", False),
                    "event_id": result.get("event_id", ""),
                    "html_link": result.get("html_link", ""),
                    "meet_link": result.get("meet_link", ""),
                    "message": result.get("message", ""),
                    "error": result.get("error") if not result.get("success") else None,
                })

            elif action_type == "list_events":
                result = await calendar_client.list_events(
                    max_results=action.get("max_results", 10),
                    time_min=action.get("time_min"),
                    time_max=action.get("time_max"),
                    calendar_id=action.get("calendar_id", "primary"),
                )
                results.append({
                    "index": i,
                    "action_type": action_type,
                    "success": result.get("success", False),
                    "count": result.get("count", 0),
                    "events": result.get("events", []),
                    "error": result.get("error") if not result.get("success") else None,
                })

            elif action_type == "update_event":
                result = await calendar_client.update_event(
                    event_id=action["event_id"],
                    summary=action.get("summary"),
                    start_datetime=action.get("start_datetime"),
                    end_datetime=action.get("end_datetime"),
                    description=action.get("description"),
                    location=action.get("location"),
                    attendees=action.get("attendees"),
                    timezone=action.get("timezone", "America/Mexico_City"),
                    calendar_id=action.get("calendar_id", "primary"),
                )
                results.append({
                    "index": i,
                    "action_type": action_type,
                    "success": result.get("success", False),
                    "event_id": action.get("event_id", ""),
                    "message": result.get("message", ""),
                    "error": result.get("error") if not result.get("success") else None,
                })

            elif action_type == "delete_event":
                result = await calendar_client.delete_event(
                    event_id=action["event_id"],
                    calendar_id=action.get("calendar_id", "primary"),
                )
                results.append({
                    "index": i,
                    "action_type": action_type,
                    "success": result.get("success", False),
                    "event_id": action.get("event_id", ""),
                    "message": result.get("message", ""),
                    "error": result.get("error") if not result.get("success") else None,
                })

            elif action_type == "check_availability":
                result = await calendar_client.check_availability(
                    emails=action["emails"],
                    time_min=action["time_min"],
                    time_max=action["time_max"],
                    timezone=action.get("timezone", "America/Mexico_City"),
                )
                results.append({
                    "index": i,
                    "action_type": action_type,
                    "success": result.get("success", False),
                    "all_available": result.get("all_available", False),
                    "availability": result.get("availability", {}),
                    "error": result.get("error") if not result.get("success") else None,
                })

            else:
                results.append({
                    "index": i,
                    "success": False,
                    "error": f"Tipo de acción desconocido: {action_type}",
                })

        except Exception as e:
            results.append({
                "index": i,
                "action_type": action_type,
                "success": False,
                "error": str(e),
            })

    return results
