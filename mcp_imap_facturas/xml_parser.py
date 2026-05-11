"""
Parser para comprobantes electrónicos del SRI Ecuador.

Estructura del XML:
  <autorizacion>
    <estado>AUTORIZADO</estado>
    <numeroAutorizacion>...</numeroAutorizacion>
    <fechaAutorizacion>...</fechaAutorizacion>
    <comprobante><![CDATA[  ← XML interno de la factura
      <factura>
        <infoTributaria>...</infoTributaria>
        <infoFactura>
          <fechaEmision>DD/MM/YYYY</fechaEmision>
          <razonSocialComprador>EMPRESA</razonSocialComprador>
          <identificacionComprador>RUC</identificacionComprador>
          <totalSinImpuestos>...</totalSinImpuestos>
          <totalConImpuestos><totalImpuesto><valor>IVA</valor></totalImpuesto></totalConImpuestos>
          <importeTotal>TOTAL</importeTotal>
        </infoFactura>
        <infoAdicional>
          <campoAdicional nombre="Email">email@cliente.com</campoAdicional>
        </infoAdicional>
      </factura>
    ]]></comprobante>
  </autorizacion>
"""

import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, Optional

TAG = "[XML_PARSER]"

COD_DOC = {
    "01": "FACTURA",
    "03": "LIQUIDACION",
    "04": "NOTA_CREDITO",
    "05": "NOTA_DEBITO",
    "06": "GUIA_REMISION",
    "07": "RETENCION",
}


def _log(msg: str) -> None:
    print(f"{TAG} {msg}", file=sys.stderr, flush=True)


def _to_float(val: Optional[str]) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None


def parse_invoice_xml(xml_bytes: bytes) -> Optional[Dict[str, Any]]:
    """
    Parsea el XML de autorización del SRI y extrae los datos de la factura.

    Retorna un dict con los campos de imap_facturas, o None si el XML
    no es válido o el comprobante no está autorizado.
    """
    try:
        root = ET.fromstring(xml_bytes.decode("utf-8", errors="replace"))
    except ET.ParseError as exc:
        _log(f"ERROR parseando XML raíz: {exc}")
        return None

    # Solo procesamos comprobantes autorizados
    estado = (root.findtext("estado") or "").strip().upper()
    if estado != "AUTORIZADO":
        _log(f"Comprobante no autorizado: estado={estado!r}")
        return None

    numero_autorizacion = (root.findtext("numeroAutorizacion") or "").strip()

    # El comprobante es CDATA → su texto es el XML interno de la factura
    comprobante_node = root.find("comprobante")
    if comprobante_node is None or not (comprobante_node.text or "").strip():
        _log("Nodo <comprobante> vacío o ausente")
        return None

    try:
        inner = ET.fromstring(comprobante_node.text.strip())
    except ET.ParseError as exc:
        _log(f"ERROR parseando XML interno del comprobante: {exc}")
        return None

    # ── infoTributaria (emisor + tipo de documento) ───────────────────────
    info_trib = inner.find("infoTributaria")
    cod_doc   = (info_trib.findtext("codDoc") or "").strip() if info_trib is not None else ""
    tipo_doc  = COD_DOC.get(cod_doc, f"DOC_{cod_doc}" if cod_doc else "DESCONOCIDO")

    estab      = (info_trib.findtext("estab")      or "") if info_trib is not None else ""
    pto_emi    = (info_trib.findtext("ptoEmi")     or "") if info_trib is not None else ""
    secuencial = (info_trib.findtext("secuencial") or "") if info_trib is not None else ""
    doc_numero = (
        f"{estab}-{pto_emi}-{secuencial}"
        if estab and pto_emi and secuencial
        else numero_autorizacion
    )

    # ── infoFactura (datos del comprobante) ───────────────────────────────
    info_fac = inner.find("infoFactura")

    doc_fecha = None
    if info_fac is not None:
        fecha_str = (info_fac.findtext("fechaEmision") or "").strip()
        if fecha_str:
            try:
                doc_fecha = datetime.strptime(fecha_str, "%d/%m/%Y").date()
            except ValueError:
                _log(f"Fecha inválida: {fecha_str!r}")

    empresa_nombre = (
        (info_fac.findtext("razonSocialComprador") or "").strip()
        if info_fac is not None else ""
    ) or None

    empresa_ruc = (
        (info_fac.findtext("identificacionComprador") or "").strip()
        if info_fac is not None else ""
    ) or None

    subtotal = _to_float(info_fac.findtext("totalSinImpuestos") if info_fac is not None else None)
    total    = _to_float(info_fac.findtext("importeTotal")      if info_fac is not None else None)

    # IVA = suma de <valor> en <totalImpuesto> donde <codigo>=2
    iva = 0.0
    if info_fac is not None:
        for imp in info_fac.findall(".//totalImpuesto"):
            if (imp.findtext("codigo") or "").strip() == "2":
                iva += _to_float(imp.findtext("valor")) or 0.0
    iva = round(iva, 2)

    # Descripción: concatenar todas las <descripcion> de <detalles>
    descripciones = [
        d.findtext("descripcion", "").strip()
        for d in inner.findall(".//detalles/detalle")
        if d.findtext("descripcion", "").strip()
    ]
    descripcion = " | ".join(descripciones) or None

    _log(
        f"Parseado OK: {tipo_doc} {doc_numero} | "
        f"{empresa_nombre!r} ({empresa_ruc}) | "
        f"subtotal={subtotal} iva={iva} total={total} | "
        f"desc={descripcion!r}"
    )

    return {
        "doc_numero":     doc_numero,
        "doc_fecha":      doc_fecha,
        "empresa_ruc":    empresa_ruc,
        "empresa_nombre": empresa_nombre,
        "subtotal":       subtotal,
        "iva":            iva,
        "total":          total,
        "tipo_doc":       tipo_doc,
        "descripcion":    descripcion,
    }
