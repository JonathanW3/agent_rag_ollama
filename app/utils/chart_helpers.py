import re
import json
from .json_sanitize import sanitize_llm_json


def parse_chart_actions(text: str) -> tuple[list[dict], str]:
    """Parsea bloques [CHART_ACTION]{json}[/CHART_ACTION] de la respuesta del LLM.

    Returns:
        Tupla de (lista de specs Plotly, texto limpio sin bloques).
    """
    pattern = r'\*{0,2}\[CHART_ACTION\]\*{0,2}(.*?)\*{0,2}\[/CHART_ACTION\]\*{0,2}'
    actions: list[dict] = []

    for match in re.finditer(pattern, text, re.DOTALL):
        raw_json = match.group(1).strip()
        if not raw_json:
            actions.append({"_parse_error": "Bloque CHART_ACTION vacío", "_raw": ""})
            continue
        sanitized = sanitize_llm_json(raw_json)
        if not sanitized.strip():
            actions.append({"_parse_error": "JSON vacío después de sanitizar", "_raw": raw_json})
            continue
        try:
            spec = json.loads(sanitized)
            error = _validate_plotly_spec(spec)
            if error:
                actions.append({"_parse_error": error, "_raw": raw_json})
            else:
                actions.append(spec)
        except json.JSONDecodeError as e:
            actions.append({"_parse_error": f"JSON inválido: {e}", "_raw": raw_json})

    cleaned = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return actions, cleaned


def _validate_plotly_spec(spec: dict) -> str | None:
    """Valida la estructura básica de un spec Plotly. Retorna mensaje de error o None si es válido."""
    if not isinstance(spec.get("data"), list):
        return "Campo 'data' obligatorio y debe ser una lista de trazas"
    if len(spec["data"]) == 0:
        return "Campo 'data' no puede estar vacío"
    for i, trace in enumerate(spec["data"]):
        if not isinstance(trace, dict):
            return f"Traza {i} debe ser un objeto/dict"
        if "type" not in trace:
            return f"Traza {i} debe tener campo 'type' (bar, line, scatter, pie, etc.)"
    if "layout" in spec and not isinstance(spec["layout"], dict):
        return "Campo 'layout' debe ser un objeto/dict"
    return None
