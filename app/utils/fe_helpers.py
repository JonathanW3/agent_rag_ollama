import re
import sys
import json
from .json_sanitize import sanitize_llm_json


def _log(*args):
    print("[FE_HELPERS]", *args, file=sys.stderr, flush=True)


def parse_fe_actions(text: str) -> tuple[list[dict], str]:
    """Parsea bloques [FE_ACTION]{json}[/FE_ACTION] de la respuesta del LLM.

    Returns:
        Tupla de (lista de acciones FE, texto limpio sin bloques).
    """
    # El tag de apertura debe estar en su propia línea (evita capturar [FE_ACTION] inline en texto).
    # Acepta: [FE_ACTION], **[FE_ACTION]**, con espacios/saltos alrededor.
    pattern = r'(?m)^\s*\*{0,2}\[FE_ACTION\]\*{0,2}\s*\n(.*?)\n?\s*\*{0,2}\[/FE_ACTION\]\*{0,2}'
    actions: list[dict] = []

    for match in re.finditer(pattern, text, re.DOTALL | re.MULTILINE):
        raw_json = match.group(1).strip()
        _log(f"raw_json capturado (repr): {repr(raw_json[:200])}")
        if not raw_json:
            actions.append({"_parse_error": "Bloque FE_ACTION vacío", "_raw": ""})
            continue
        sanitized = sanitize_llm_json(raw_json)
        _log(f"sanitized (repr): {repr(sanitized[:200])}")
        if not sanitized.strip():
            actions.append({"_parse_error": "JSON vacío después de sanitizar", "_raw": raw_json})
            continue
        try:
            action = json.loads(sanitized.strip())
            if "tool" not in action:
                actions.append({"_parse_error": "Falta campo 'tool'", "_raw": raw_json})
            else:
                actions.append(action)
        except json.JSONDecodeError as e:
            _log(f"JSONDecodeError en: {repr(sanitized[:300])}")
            actions.append({"_parse_error": f"JSON inválido: {e}", "_raw": raw_json})

    cleaned = re.sub(pattern, '', text, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return actions, cleaned


async def execute_fe_actions(actions: list[dict], fe_client) -> list[dict]:
    """Ejecuta acciones FEPA usando el cliente MCP FE."""
    results: list[dict] = []

    for i, action in enumerate(actions):
        if "_parse_error" in action:
            results.append({"index": i, "success": False, "error": action["_parse_error"]})
            continue

        tool = action.get("tool")
        # Quitar la clave "tool" antes de pasar como argumentos
        args = {k: v for k, v in action.items() if k != "tool"}

        try:
            data = await fe_client.call_tool(tool, args)
            success = "error" not in data
            results.append({
                "index": i,
                "tool": tool,
                "success": success,
                "data": data,
                "error": data.get("error") if not success else None,
            })
        except Exception as e:
            results.append({
                "index": i,
                "tool": tool,
                "success": False,
                "error": str(e),
            })

    return results
