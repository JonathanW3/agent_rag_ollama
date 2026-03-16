import re


def _find_sentence_boundary(text: str, pos: int, search_range: int = 200) -> int:
    """Busca el fin de oración más cercano a `pos` dentro de un rango.

    Retorna la posición justo después del delimitador (.!?\\n) más cercano,
    o `pos` si no se encuentra ninguno en el rango.
    """
    # Buscar hacia atrás desde pos hasta pos - search_range
    search_start = max(0, pos - search_range)
    region = text[search_start:pos]

    # Buscar el último fin de oración en la región
    match = None
    for m in re.finditer(r'[.!?]\s|\n\n', region):
        match = m

    if match:
        return search_start + match.end()

    return pos


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    """Divide texto en chunks respetando límites de oración cuando es posible.

    Intenta cortar en el fin de oración más cercano al chunk_size. Si no
    encuentra uno dentro de un rango razonable, corta en el límite duro
    para garantizar progreso.
    """
    if not text or not text.strip():
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        if end >= text_len:
            # Último chunk: tomar todo lo que queda
            chunk = text[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Intentar ajustar el corte a un fin de oración
        boundary = _find_sentence_boundary(text, end)
        if boundary > start:
            end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Avanzar con overlap, pero desde el boundary real
        start = max(start + 1, end - overlap)

    return chunks
