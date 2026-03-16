import re
import json
from .json_sanitize import sanitize_llm_json


def parse_email_actions(text: str) -> tuple[list[dict], str]:
    """Parsea bloques [EMAIL_ACTION]{json}[/EMAIL_ACTION] de la respuesta del LLM.

    Returns:
        Tupla de (lista de acciones email, texto limpio sin bloques).
    """
    pattern = r'\[EMAIL_ACTION\](.*?)\[/EMAIL_ACTION\]'
    actions: list[dict] = []

    for match in re.finditer(pattern, text, re.DOTALL):
        raw_json = match.group(1).strip()
        if not raw_json:
            actions.append({"_parse_error": "Bloque EMAIL_ACTION vacío", "_raw": ""})
            continue
        sanitized = sanitize_llm_json(raw_json)
        if not sanitized.strip():
            actions.append({"_parse_error": "JSON vacío después de sanitizar", "_raw": raw_json})
            continue
        try:
            action = json.loads(sanitized)
            if all(k in action for k in ("to", "subject", "body")):
                actions.append(action)
            else:
                actions.append({"_parse_error": "Faltan campos obligatorios (to, subject, body)", "_raw": raw_json})
        except json.JSONDecodeError as e:
            actions.append({"_parse_error": f"JSON inválido: {e}", "_raw": raw_json})

    cleaned = re.sub(pattern, '', text, flags=re.DOTALL).strip()
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return actions, cleaned


def md_to_html(text: str) -> str:
    """Convierte Markdown a HTML con soporte para tablas, negritas, listas, etc."""
    import markdown as _md
    return _md.markdown(
        text,
        extensions=["tables", "nl2br", "sane_lists", "fenced_code"],
    )


def wrap_email_template(body: str, subject: str, is_html: bool, agent_name: str, sender_email: str) -> str:
    """Envuelve el contenido del email en una plantilla HTML corporativa.

    Si el body contiene sintaxis Markdown (**negritas**, tablas, listas, etc.)
    se convierte automáticamente a HTML antes de inyectarlo en la plantilla.
    """
    from datetime import datetime

    # Convertir Markdown → HTML si el body no es HTML puro
    if not is_html:
        body = md_to_html(body)
    else:
        # Incluso si es HTML, puede tener fragmentos Markdown mezclados
        # Detectar si hay sintaxis MD dentro del HTML (**, ##, -, |)
        if any(marker in body for marker in ['**', '## ', '- ', '| ']):
            body = md_to_html(body)

    date_str = datetime.now().strftime('%d/%m/%Y %H:%M')
    initial = agent_name[0].upper() if agent_name else "A"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#f0f2f5;font-family:'Segoe UI',Roboto,Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased;">

  <!-- Wrapper -->
  <table width="100%" cellpadding="0" cellspacing="0" role="presentation" style="background-color:#f0f2f5;padding:32px 16px;">
    <tr><td align="center">

      <!-- Card -->
      <table width="680" cellpadding="0" cellspacing="0" role="presentation" style="background-color:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.06);border:1px solid #e3e8ee;">

        <!-- ══ HEADER ══ -->
        <tr>
          <td style="background:linear-gradient(135deg,#0f3460 0%,#16537e 50%,#1a6fa0 100%);padding:0;">
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
              <tr>
                <td style="padding:32px 40px 28px;">
                  <table cellpadding="0" cellspacing="0" role="presentation">
                    <tr>
                      <td style="vertical-align:middle;padding-right:16px;">
                        <div style="width:48px;height:48px;border-radius:12px;background:rgba(255,255,255,0.15);text-align:center;line-height:48px;font-size:20px;font-weight:700;color:#ffffff;border:2px solid rgba(255,255,255,0.25);">
                          {initial}
                        </div>
                      </td>
                      <td style="vertical-align:middle;">
                        <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:700;letter-spacing:0.3px;line-height:1.3;">
                          {agent_name}
                        </h1>
                        <p style="margin:4px 0 0;color:rgba(255,255,255,0.7);font-size:12px;font-weight:500;letter-spacing:0.5px;text-transform:uppercase;">
                          Reporte Automatizado
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ══ SUBJECT BAR ══ -->
        <tr>
          <td style="background-color:#f8fafc;padding:16px 40px;border-bottom:1px solid #e3e8ee;">
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
              <tr>
                <td>
                  <p style="margin:0;color:#0f3460;font-size:15px;font-weight:600;line-height:1.4;">
                    {subject}
                  </p>
                </td>
                <td style="text-align:right;white-space:nowrap;">
                  <span style="color:#8896a6;font-size:12px;font-weight:500;">
                    {date_str}
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- ══ BODY ══ -->
        <tr>
          <td style="padding:32px 40px;color:#2d3748;font-size:14px;line-height:1.8;">
            <style>
              .email-body h1 {{ color:#0f3460;font-size:20px;font-weight:700;margin:24px 0 12px;padding-bottom:8px;border-bottom:2px solid #e3e8ee; }}
              .email-body h2 {{ color:#16537e;font-size:17px;font-weight:700;margin:20px 0 10px; }}
              .email-body h3 {{ color:#1a6fa0;font-size:15px;font-weight:600;margin:16px 0 8px; }}
              .email-body p {{ margin:0 0 12px;color:#2d3748; }}
              .email-body strong {{ color:#1a202c; }}
              .email-body ul, .email-body ol {{ margin:8px 0 16px;padding-left:24px; }}
              .email-body li {{ margin:4px 0;color:#2d3748; }}
              .email-body table {{ width:100%;border-collapse:collapse;margin:16px 0;font-size:13px; }}
              .email-body th {{ background-color:#0f3460;color:#ffffff;padding:10px 14px;text-align:left;font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.5px; }}
              .email-body td {{ padding:10px 14px;border-bottom:1px solid #e3e8ee;color:#2d3748; }}
              .email-body tr:nth-child(even) {{ background-color:#f8fafc; }}
              .email-body tr:hover {{ background-color:#edf2f7; }}
              .email-body code {{ background:#f1f5f9;padding:2px 6px;border-radius:4px;font-size:13px;color:#e53e3e;font-family:'Courier New',monospace; }}
              .email-body pre {{ background:#1a202c;color:#e2e8f0;padding:16px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.5;margin:12px 0; }}
              .email-body pre code {{ background:none;color:inherit;padding:0; }}
              .email-body blockquote {{ border-left:4px solid #1a6fa0;margin:12px 0;padding:12px 20px;background:#f0f7ff;border-radius:0 8px 8px 0;color:#2d3748; }}
              .email-body hr {{ border:none;border-top:1px solid #e3e8ee;margin:20px 0; }}
              .email-body a {{ color:#1a6fa0;text-decoration:none;font-weight:500; }}
            </style>
            <div class="email-body">
              {body}
            </div>
          </td>
        </tr>

        <!-- ══ FOOTER ══ -->
        <tr>
          <td style="padding:0 40px;">
            <hr style="border:none;border-top:1px solid #e3e8ee;margin:0;">
          </td>
        </tr>
        <tr>
          <td style="padding:24px 40px 28px;background-color:#f8fafc;">
            <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
              <tr>
                <td style="vertical-align:top;">
                  <p style="margin:0 0 2px;color:#2d3748;font-size:13px;font-weight:700;">
                    Gerencia de Inteligencia de Negocio
                  </p>
                  <p style="margin:0 0 2px;color:#718096;font-size:12px;">
                    Cadena de Farmacias
                  </p>
                  <p style="margin:0;color:#a0aec0;font-size:12px;">
                    {sender_email}
                  </p>
                </td>
                <td style="text-align:right;vertical-align:bottom;">
                  <p style="margin:0;color:#a0aec0;font-size:11px;">
                    Generado por IA<br>{date_str}
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

      </table>

      <!-- Disclaimer -->
      <table width="680" cellpadding="0" cellspacing="0" role="presentation">
        <tr>
          <td style="padding:16px 40px 0;text-align:center;">
            <p style="margin:0;color:#a0aec0;font-size:11px;line-height:1.5;">
              Este correo fue generado de forma automatizada por un sistema de inteligencia artificial.<br>
              Si recibiste este mensaje por error, por favor ignóralo.
            </p>
          </td>
        </tr>
      </table>

    </td></tr>
  </table>

</body>
</html>"""


async def execute_email_actions(
    actions: list[dict],
    smtp_config: dict,
    email_client,
    agent_name: str = "Asistente IA",
) -> list[dict]:
    """Ejecuta acciones de email usando el smtp_config del agente (nunca del LLM)."""
    results: list[dict] = []
    sender_email = smtp_config.get("email", "")

    for i, action in enumerate(actions):
        if "_parse_error" in action:
            results.append({"index": i, "success": False, "error": action["_parse_error"]})
            continue
        try:
            # Envolver el body en la plantilla corporativa
            wrapped_body = wrap_email_template(
                body=action["body"],
                subject=action["subject"],
                is_html=action.get("html", False),
                agent_name=agent_name,
                sender_email=sender_email,
            )
            result = await email_client.send_email(
                smtp_config=smtp_config,
                to=action["to"],
                subject=action["subject"],
                body=wrapped_body,
                html=True,  # Siempre HTML porque la plantilla lo es
                cc=action.get("cc"),
                bcc=action.get("bcc"),
            )
            results.append({
                "index": i,
                "to": action["to"],
                "subject": action["subject"],
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "error": result.get("error") if not result.get("success") else None,
            })
        except Exception as e:
            results.append({
                "index": i,
                "to": action.get("to", "desconocido"),
                "subject": action.get("subject", ""),
                "success": False,
                "error": str(e),
            })

    return results
