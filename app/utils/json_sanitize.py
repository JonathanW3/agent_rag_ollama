import re
from starlette.middleware.base import BaseHTTPMiddleware


def sanitize_json_body(text: str) -> str:
    """Escapa caracteres de control literales dentro de strings JSON.

    JSON no permite caracteres de control (< 0x20) sin escapar dentro de
    strings.  Swagger UI y curl multi-linea los insertan literalmente cuando
    el usuario pega texto con saltos de linea.  Esta funcion los convierte a
    sus representaciones de escape (\\n, \\r, \\t, \\uXXXX) sin tocar la
    estructura del JSON.
    """
    result: list[str] = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == "\\" and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ord(ch) < 0x20:
            # Caracter de control dentro de un string → escapar
            if ch == "\n":
                result.append("\\n")
            elif ch == "\r":
                result.append("\\r")
            elif ch == "\t":
                result.append("\\t")
            else:
                result.append(f"\\u{ord(ch):04x}")
        else:
            result.append(ch)

    return "".join(result)


def sanitize_llm_json(raw: str) -> str:
    """Repara JSON generado por LLMs que contiene errores comunes.

    Problemas que corrige:
    - Saltos de línea literales dentro de strings (los escapa como \\n)
    - Bloques markdown ```json ... ```
    - Comillas tipográficas (\u201c \u201d) por comillas rectas
    - Trailing commas antes de } o ]
    """
    # Quitar bloques markdown
    raw = re.sub(r'^```(?:json)?\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    # Comillas tipográficas → rectas
    raw = raw.replace('\u201c', '"').replace('\u201d', '"')
    raw = raw.replace('\u2018', "'").replace('\u2019', "'")

    # Escapar saltos de línea/tabs literales DENTRO de strings JSON
    result: list[str] = []
    in_string = False
    escape_next = False
    for ch in raw:
        if escape_next:
            result.append(ch)
            escape_next = False
        elif ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            result.append('\\r')
        elif in_string and ch == '\t':
            result.append('\\t')
        else:
            result.append(ch)
    sanitized = ''.join(result)

    # Trailing commas: ,} → } y ,] → ]
    sanitized = re.sub(r',\s*([}\]])', r'\1', sanitized)
    return sanitized


class SanitizeJSONMiddleware(BaseHTTPMiddleware):
    """Middleware que sanitiza caracteres de control en bodies JSON."""

    async def dispatch(self, request, call_next):
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            raw = await request.body()
            try:
                text = raw.decode("utf-8")
                fixed = sanitize_json_body(text)
                if fixed != text:
                    # Starlette cachea el body en _body tras leerlo;
                    # hay que sobreescribir esa caché con el body limpio.
                    request._body = fixed.encode("utf-8")
            except Exception:
                pass  # Si falla, dejar que FastAPI maneje el error original
        return await call_next(request)
