"""
Helpers para procesar bloques [IMAP_FACTURAS_ACTION] generados por el LLM.

Las herramientas disponibles leen de MySQL (platform_db), no de IMAP directamente.
El buzón se sincroniza automáticamente cada hora mediante el cron imap_facturas_sync.
"""

import json
import re
from typing import Any, Dict, List, Tuple

from .json_sanitize import sanitize_llm_json


def parse_imap_facturas_actions(text: str) -> Tuple[List[Dict], str]:
    """
    Parsea bloques [IMAP_FACTURAS_ACTION]{json}[/IMAP_FACTURAS_ACTION].

    Returns:
        (lista de acciones, texto limpio sin los bloques)
    """
    pattern = r'\*{0,2}\[IMAP_FACTURAS_ACTION\]\*{0,2}(.*?)\*{0,2}\[/IMAP_FACTURAS_ACTION\]\*{0,2}'
    actions: List[Dict] = []

    for match in re.finditer(pattern, text, re.DOTALL):
        raw = match.group(1).strip()
        if not raw:
            actions.append({"_parse_error": "Bloque IMAP_FACTURAS_ACTION vacío", "_raw": ""})
            continue
        sanitized = sanitize_llm_json(raw)
        if not sanitized.strip():
            actions.append({"_parse_error": "JSON vacío tras sanitizar", "_raw": raw})
            continue
        try:
            action = json.loads(sanitized)
            if "tool" not in action:
                actions.append({"_parse_error": "Falta campo obligatorio 'tool'", "_raw": raw})
            else:
                actions.append(action)
        except json.JSONDecodeError as exc:
            actions.append({"_parse_error": f"JSON inválido: {exc}", "_raw": raw})

    cleaned = re.sub(pattern, "", text, flags=re.DOTALL).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return actions, cleaned


async def execute_imap_facturas_actions(
    actions: List[Dict],
    client,
) -> List[Dict]:
    """
    Ejecuta acciones IMAP Facturas usando el cliente de base de datos.

    Args:
        actions: Lista de dicts con 'tool' y parámetros.
        client:  Instancia de IMAPFacturasClient.

    Returns:
        Lista de resultados por acción.
    """
    results: List[Dict[str, Any]] = []

    for action in actions:
        if "_parse_error" in action:
            results.append({"tool": "unknown", "success": False, "error": action["_parse_error"]})
            continue

        tool = action.get("tool", "")
        params = {k: v for k, v in action.items() if k != "tool"}

        try:
            if tool == "facturas_del_periodo":
                required = ["since_date", "before_date"]
                missing = [f for f in required if not action.get(f)]
                if missing:
                    result = {"success": False, "error": f"facturas_del_periodo requiere: {', '.join(missing)}"}
                else:
                    result = await client.facturas_del_periodo(
                        since_date=action["since_date"],
                        before_date=action["before_date"],
                        empresa=action.get("empresa"),
                    )

            elif tool == "comparar_periodos_facturas":
                required = ["period_a_start", "period_a_end", "period_b_start", "period_b_end"]
                missing = [f for f in required if not action.get(f)]
                if missing:
                    result = {"success": False, "error": f"comparar_periodos_facturas requiere: {', '.join(missing)}"}
                else:
                    result = await client.comparar_periodos_facturas(
                        period_a_start=action["period_a_start"],
                        period_a_end=action["period_a_end"],
                        period_b_start=action["period_b_start"],
                        period_b_end=action["period_b_end"],
                    )

            elif tool == "comunicaciones_del_periodo":
                required = ["since_date", "before_date"]
                missing = [f for f in required if not action.get(f)]
                if missing:
                    result = {"success": False, "error": f"comunicaciones_del_periodo requiere: {', '.join(missing)}"}
                else:
                    result = await client.comunicaciones_del_periodo(
                        since_date=action["since_date"],
                        before_date=action["before_date"],
                        empresa=action.get("empresa"),
                    )

            else:
                result = {
                    "success": False,
                    "error": (
                        f"Tool desconocida: '{tool}'. "
                        "Disponibles: facturas_del_periodo, comparar_periodos_facturas, comunicaciones_del_periodo"
                    ),
                }

            results.append({"tool": tool, **result})

        except Exception as exc:
            results.append({"tool": tool, "success": False, "error": str(exc)})

    return results


def format_imap_facturas_results_for_history(results: List[Dict]) -> str:
    """Formatea resultados de IMAP Facturas para inyectar en el historial del LLM."""
    if not results:
        return ""

    lines: List[str] = []

    for r in results:
        tool = r.get("tool", "unknown")
        if not r.get("success"):
            lines.append(f"  ✗ {tool}: {r.get('error', 'error desconocido')}")
            continue

        if tool == "facturas_del_periodo":
            count  = r.get("count", 0)
            total  = r.get("total_importe", 0)
            period = f"{r.get('since_date')} → {r.get('before_date')}"
            filtro = f" empresa={r['empresa_filtro']!r}" if r.get("empresa_filtro") else ""
            lines.append(f"  facturas_del_periodo [{period}]{filtro} → {count} factura(s), total=${total:,.2f}:")
            for f in r.get("facturas", []):
                amt      = f"${float(f['total']):,.2f}"  if f.get("total")  is not None else "—"
                subtotal = f"${float(f['subtotal']):,.2f}" if f.get("subtotal") is not None else "—"
                iva      = f"${float(f['iva']):,.2f}"    if f.get("iva")    is not None else "—"
                empresa  = f.get("empresa_nombre") or f.get("empresa_ruc") or "SIN EMPRESA"
                lines.append(
                    f"    [{f.get('doc_fecha', '?')}] {empresa} | "
                    f"subtotal={subtotal} iva={iva} total={amt} | "
                    f"tipo={f.get('tipo_doc','?')} num={f.get('doc_numero','?')}"
                )
                if f.get("descripcion"):
                    lines.append(f"      descripcion: {f['descripcion'][:120]}")

        elif tool == "comparar_periodos_facturas":
            pa  = r.get("period_a", {})
            pb  = r.get("period_b", {})
            smr = r.get("summary", {})
            lines.append(
                f"  comparar_periodos_facturas:\n"
                f"    Período A ({pa.get('start')} → {pa.get('end')}): "
                f"{pa.get('count')} factura(s), total=${pa.get('total', 0):,.2f}\n"
                f"    Período B ({pb.get('start')} → {pb.get('end')}): "
                f"{pb.get('count')} factura(s), total=${pb.get('total', 0):,.2f}"
            )
            lines.append(f"    TABLA COMPARATIVA ({smr.get('total_companies')} empresa(s)):")
            lines.append(f"    {'Empresa':<40} {'A cant':>6} {'A total':>10} {'B cant':>6} {'B total':>10}  Estado")
            lines.append(f"    {'-'*40} {'-'*6} {'-'*10} {'-'*6} {'-'*10}  {'-'*12}")
            for row in r.get("table", []):
                a_amt  = f"${float(row['period_a_total']):,.2f}" if row.get("period_a_total") is not None else "—"
                b_amt  = f"${float(row['period_b_total']):,.2f}" if row.get("period_b_total") is not None else "—"
                estado = "⚠ FALTA" if row["status"] == "FALTA EN B" else ("★ NUEVO" if row["status"] == "NUEVO EN B" else "✓")
                lines.append(
                    f"    {row['company'][:40]:<40} {row['period_a_count']:>6} {a_amt:>10} "
                    f"{row['period_b_count']:>6} {b_amt:>10}  {estado}"
                )
            missing = r.get("missing_in_b", [])
            if missing:
                lines.append(f"\n    ⚠ EMPRESAS FALTANTES EN PERÍODO B ({len(missing)}):")
                for co in missing:
                    lines.append(f"      · {co}")
            else:
                lines.append("\n    ✓ Todas las empresas del período A ya tienen factura en B.")

        elif tool == "comunicaciones_del_periodo":
            count  = r.get("count", 0)
            period = f"{r.get('since_date')} → {r.get('before_date')}"
            filtro = f" empresa={r['empresa_filtro']!r}" if r.get("empresa_filtro") else ""
            lines.append(f"  comunicaciones_del_periodo [{period}]{filtro} → {count} comunicación(es):")
            for c in r.get("comunicaciones", []):
                lines.append(
                    f"    [{c.get('email_fecha', '?')}] De: {(c.get('de_email') or '?')[:50]}  "
                    f"Asunto: {(c.get('asunto') or '')[:60]}"
                )
                if c.get("cuerpo"):
                    lines.append(f"      {c['cuerpo'][:200]}")

    return "[RESULTADO DE IMAP FACTURAS]\n" + "\n".join(lines) + "\n[/RESULTADO DE IMAP FACTURAS]"
