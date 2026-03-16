from fastapi import APIRouter, HTTPException, Query
from ..schemas import EmailSendRequest
from ..agents import get_agent
from mcp_email.client import get_email_client
from mcp_sqlite.client import get_mcp_client

router = APIRouter(prefix="/email", tags=["📧 Email"])


@router.post("/send", summary="Enviar email desde un agente")
async def send_email_endpoint(req: EmailSendRequest):
    """
    Envía un email usando la configuración SMTP del agente especificado.
    El agente debe tener smtp_config configurado.
    """
    # Verificar que el agente existe
    agent = get_agent(req.agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agente '{req.agent_id}' no encontrado")

    # Verificar que el agente tiene configuración SMTP
    smtp_config = agent.get("smtp_config")
    if not smtp_config:
        raise HTTPException(
            status_code=400,
            detail=f"El agente '{req.agent_id}' no tiene configuración SMTP. Actualiza el agente con smtp_config."
        )

    # Enviar email
    try:
        email_client = get_email_client()
        result = await email_client.send_email(
            smtp_config=smtp_config,
            to=req.to,
            subject=req.subject,
            body=req.body,
            cc=req.cc,
            bcc=req.bcc,
            html=req.html,
            attachments=req.attachments
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Error desconocido al enviar email")
            )

        # Registrar en SQLite si MCP está habilitado
        try:
            mcp_client = get_mcp_client()
            await mcp_client.log_agent_action(
                agent_id=req.agent_id,
                action="email_sent",
                details={
                    "to": req.to,
                    "subject": req.subject,
                    "cc": req.cc or [],
                    "bcc": req.bcc or []
                },
                success=True
            )
        except Exception as e:
            print(f"Error logging email to SQLite: {e}")

        return {
            "status": "ok",
            "message": result.get("message"),
            "agent_id": req.agent_id,
            "recipients": result.get("recipients", [req.to])
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error enviando email: {str(e)}"
        )


@router.get("/providers", summary="Listar proveedores SMTP")
async def list_email_providers():
    """
    Lista los proveedores SMTP predefinidos con sus configuraciones.
    Incluye Gmail, Outlook, Yahoo, Office365.
    """
    try:
        email_client = get_email_client()
        result = await email_client.list_providers()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listando proveedores: {str(e)}"
        )


@router.post("/validate", summary="Validar email")
async def validate_email_endpoint(email: str = Query(..., description="Email a validar", example="usuario@example.com")):
    """Valida el formato de un email."""
    try:
        email_client = get_email_client()
        result = await email_client.validate_email(email)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error validando email: {str(e)}"
        )
