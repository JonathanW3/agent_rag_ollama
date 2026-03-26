from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from ..schemas import (
    CalendarEventCreateRequest,
    CalendarEventUpdateRequest,
    CalendarCheckAvailabilityRequest,
)
from mcp_google_calendar.client import get_calendar_client
from mcp_sqlite.client import get_mcp_client

router = APIRouter(prefix="/calendar", tags=["📅 Google Calendar"])


@router.post("/events", summary="Crear evento/reunión")
async def create_event(req: CalendarEventCreateRequest):
    """
    Crea un evento o reunión en Google Calendar.
    Opcionalmente agrega enlace de Google Meet y participantes.
    """
    try:
        client = get_calendar_client()
        result = await client.create_event(
            summary=req.summary,
            start_datetime=req.start_datetime,
            end_datetime=req.end_datetime,
            description=req.description,
            location=req.location,
            attendees=req.attendees,
            timezone=req.timezone,
            add_meet=req.add_meet,
            calendar_id=req.calendar_id,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Error creando evento"),
            )

        # Log en SQLite
        try:
            mcp_client = get_mcp_client()
            await mcp_client.log_agent_action(
                agent_id=req.agent_id or "system",
                action="calendar_event_created",
                details={
                    "summary": req.summary,
                    "start": req.start_datetime,
                    "end": req.end_datetime,
                    "attendees": req.attendees or [],
                },
                success=True,
            )
        except Exception as e:
            print(f"Error logging calendar event to SQLite: {e}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creando evento: {str(e)}")


@router.get("/events", summary="Listar eventos")
async def list_events(
    max_results: int = Query(default=10, ge=1, le=100, description="Número máximo de eventos"),
    time_min: Optional[str] = Query(default=None, description="Fecha/hora mínima ISO 8601"),
    time_max: Optional[str] = Query(default=None, description="Fecha/hora máxima ISO 8601"),
    calendar_id: str = Query(default="primary", description="ID del calendario"),
):
    """
    Lista eventos del calendario. Por defecto muestra los próximos 10 eventos.
    """
    try:
        client = get_calendar_client()
        result = await client.list_events(
            max_results=max_results,
            time_min=time_min,
            time_max=time_max,
            calendar_id=calendar_id,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Error listando eventos"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listando eventos: {str(e)}")


@router.put("/events/{event_id}", summary="Actualizar evento")
async def update_event(event_id: str, req: CalendarEventUpdateRequest):
    """
    Actualiza un evento existente. Solo se modifican los campos proporcionados.
    """
    try:
        client = get_calendar_client()
        result = await client.update_event(
            event_id=event_id,
            summary=req.summary,
            start_datetime=req.start_datetime,
            end_datetime=req.end_datetime,
            description=req.description,
            location=req.location,
            attendees=req.attendees,
            timezone=req.timezone,
            calendar_id=req.calendar_id,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Error actualizando evento"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando evento: {str(e)}")


@router.delete("/events/{event_id}", summary="Eliminar evento")
async def delete_event(
    event_id: str,
    calendar_id: str = Query(default="primary", description="ID del calendario"),
):
    """Elimina un evento del calendario y notifica a los participantes."""
    try:
        client = get_calendar_client()
        result = await client.delete_event(
            event_id=event_id,
            calendar_id=calendar_id,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Error eliminando evento"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error eliminando evento: {str(e)}")


@router.post("/availability", summary="Verificar disponibilidad")
async def check_availability(req: CalendarCheckAvailabilityRequest):
    """
    Verifica la disponibilidad de participantes en un rango de tiempo
    usando Google Calendar FreeBusy.
    """
    try:
        client = get_calendar_client()
        result = await client.check_availability(
            emails=req.emails,
            time_min=req.time_min,
            time_max=req.time_max,
            timezone=req.timezone,
        )

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Error verificando disponibilidad"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verificando disponibilidad: {str(e)}")


@router.get("/list", summary="Listar calendarios")
async def list_calendars():
    """Lista todos los calendarios disponibles del usuario autenticado."""
    try:
        client = get_calendar_client()
        result = await client.list_calendars()

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Error listando calendarios"),
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listando calendarios: {str(e)}")
