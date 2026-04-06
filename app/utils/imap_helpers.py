import re
import json
from .json_sanitize import sanitize_llm_json


def parse_imap_actions(text: str) -> tuple[list[dict], str]:
    """Parsea bloques [IMAP_ACTION]{json}[/IMAP_ACTION] de la respuesta del LLM.

    Returns:
        Tupla de (lista de acciones IMAP, texto limpio sin bloques).
    """
    pattern = r'\*{0,2}\[IMAP_ACTION\]\*{0,2}(.*?)\*{0,2}\[/IMAP_ACTION\]\*{0,2}'
    actions: list[dict] = []

    for match in re.finditer(pattern, text, re.DOTALL):
        raw_json = match.group(1).strip()
        if not raw_json:
            actions.append({"_parse_error": "Bloque IMAP_ACTION vacío", "_raw": ""})
            continue
        sanitized = sanitize_llm_json(raw_json)
        if not sanitized.strip():
            actions.append({"_parse_error": "JSON vacío después de sanitizar", "_raw": raw_json})
            continue
        try:
            action = json.loads(sanitized)
            if "action" not in action:
                actions.append({"_parse_error": "Falta campo obligatorio 'action'", "_raw": raw_json})
            else:
                actions.append(action)
        except json.JSONDecodeError as e:
            actions.append({"_parse_error": f"JSON inválido: {e}", "_raw": raw_json})

    cleaned = re.sub(pattern, '', text, flags=re.DOTALL).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return actions, cleaned


async def execute_imap_actions(
    actions: list[dict],
    imap_config: dict,
    imap_client,
) -> list[dict]:
    """Ejecuta acciones IMAP y retorna resultados estructurados."""
    results: list[dict] = []

    for action in actions:
        if "_parse_error" in action:
            results.append({"success": False, "action": "unknown", "error": action["_parse_error"]})
            continue

        action_type = action.get("action", "")
        try:
            if action_type == "read_inbox":
                result = await imap_client.read_inbox(
                    imap_config=imap_config,
                    limit=int(action.get("limit", 10)),
                    folder=action.get("folder", "INBOX"),
                )
            elif action_type == "search_emails":
                result = await imap_client.search_emails(
                    imap_config=imap_config,
                    from_addr=action.get("from"),
                    subject=action.get("subject"),
                    since_date=action.get("since"),
                    keyword=action.get("keyword"),
                    unseen_only=bool(action.get("unseen_only", False)),
                    limit=int(action.get("limit", 10)),
                    folder=action.get("folder", "INBOX"),
                )
            elif action_type == "read_email":
                email_id = action.get("id") or action.get("email_id")
                if not email_id:
                    result = {"success": False, "error": "Falta campo 'id' del email"}
                else:
                    result = await imap_client.read_email(
                        imap_config=imap_config,
                        email_id=str(email_id),
                        folder=action.get("folder", "INBOX"),
                    )
            else:
                result = {"success": False, "error": f"Acción IMAP desconocida: '{action_type}'. Use: read_inbox, search_emails, read_email"}

            results.append({"action": action_type, **result})

        except Exception as e:
            results.append({"action": action_type, "success": False, "error": str(e)})

    return results


def format_imap_results_for_history(results: list[dict]) -> str:
    """Formatea los resultados IMAP para inyectar en el historial de conversación."""
    if not results:
        return ""

    lines = []
    for r in results:
        action = r.get("action", "unknown")
        if not r.get("success"):
            lines.append(f"  - FALLÓ {action}: {r.get('error', 'error desconocido')}")
            continue

        if action in ("read_inbox", "search_emails"):
            count = r.get("count", 0)
            emails = r.get("emails", [])
            folder = r.get("folder", "INBOX")
            criteria = r.get("criteria", "")
            header = f"  - {action.upper()} ({folder})"
            if criteria and criteria != "ALL":
                header += f" | Criterio: {criteria}"
            header += f" | {count} email(s) encontrado(s)"
            lines.append(header)
            for em in emails:
                lines.append(
                    f"    [ID:{em['id']}] De: {em['from']} | Asunto: {em['subject']} | Fecha: {em['date']}"
                )
                if em.get("body"):
                    preview = em["body"][:200].replace("\n", " ")
                    lines.append(f"    Contenido: {preview}...")

        elif action == "read_email":
            em = r.get("email", {})
            lines.append(f"  - READ_EMAIL [ID:{em.get('id')}]")
            lines.append(f"    De: {em.get('from')} | Para: {em.get('to')}")
            lines.append(f"    Asunto: {em.get('subject')} | Fecha: {em.get('date')}")
            if em.get("has_attachments"):
                lines.append("    Adjuntos: Sí")
            if em.get("body"):
                lines.append(f"    Contenido:\n{em['body']}")

    return "[RESULTADO DE IMAP]\n" + "\n".join(lines) + "\n[/RESULTADO DE IMAP]"
