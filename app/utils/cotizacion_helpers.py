"""
Helpers para parsear y procesar bloques [COTIZACION_ACTION] generados por el LLM.
"""

import re
import json
from .json_sanitize import sanitize_llm_json


def parse_cotizacion_actions(text: str) -> tuple[list[dict], str]:
    """Parsea bloques [COTIZACION_ACTION]{json}[/COTIZACION_ACTION] de la respuesta del LLM.

    Returns:
        Tupla de (lista de acciones cotización, texto limpio sin bloques).
    """
    pattern = r'\*{0,2}\[COTIZACION_ACTION\]\*{0,2}(.*?)\*{0,2}\[/COTIZACION_ACTION\]\*{0,2}'
    actions: list[dict] = []

    for match in re.finditer(pattern, text, re.DOTALL):
        raw_json = match.group(1).strip()
        if not raw_json:
            actions.append({"_parse_error": "Bloque COTIZACION_ACTION vacío", "_raw": ""})
            continue
        sanitized = sanitize_llm_json(raw_json)
        if not sanitized.strip():
            actions.append({"_parse_error": "JSON vacío después de sanitizar", "_raw": raw_json})
            continue
        try:
            action = json.loads(sanitized)
            # Validar campos mínimos
            if "cliente" not in action:
                actions.append({"_parse_error": "Falta campo 'cliente'", "_raw": raw_json})
            elif "productos" not in action:
                actions.append({"_parse_error": "Falta campo 'productos'", "_raw": raw_json})
            else:
                actions.append(action)
        except json.JSONDecodeError as e:
            actions.append({"_parse_error": f"JSON inválido: {e}", "_raw": raw_json})

    cleaned = re.sub(pattern, '', text, flags=re.DOTALL).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return actions, cleaned
