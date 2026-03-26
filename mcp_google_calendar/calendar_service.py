"""
Google Calendar Service

Maneja autenticación OAuth2 y operaciones CRUD con Google Calendar API.
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes necesarios para Google Calendar
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

# Rutas por defecto para credenciales
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials", "credentials.json")
DEFAULT_TOKEN_PATH = os.path.join(BASE_DIR, "credentials", "token.json")


class GoogleCalendarService:
    """Servicio para interactuar con Google Calendar API."""

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        token_path: Optional[str] = None,
    ):
        self.credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
        self.token_path = token_path or DEFAULT_TOKEN_PATH
        self._service = None

    def _get_credentials(self) -> Credentials:
        """Obtiene credenciales válidas, renovando o solicitando auth si es necesario."""
        creds = None

        # Cargar token existente
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)

        # Si no hay credenciales válidas, renovar o autenticar
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(
                        f"No se encontró credentials.json en: {self.credentials_path}. "
                        "Descarga el archivo desde Google Cloud Console y colócalo en "
                        "mcp_google_calendar/credentials/credentials.json"
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Guardar token para futuras ejecuciones
            with open(self.token_path, "w") as token_file:
                token_file.write(creds.to_json())

        return creds

    def _get_service(self):
        """Obtiene o crea la instancia del servicio de Google Calendar."""
        if self._service is None:
            creds = self._get_credentials()
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    async def list_events(
        self,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Lista eventos del calendario.

        Args:
            max_results: Número máximo de eventos a retornar
            time_min: Fecha/hora mínima (ISO 8601), default=ahora
            time_max: Fecha/hora máxima (ISO 8601), opcional
            calendar_id: ID del calendario (default: primary)
        """
        try:
            service = self._get_service()

            if not time_min:
                time_min = datetime.utcnow().isoformat() + "Z"

            params = {
                "calendarId": calendar_id,
                "timeMin": time_min,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if time_max:
                params["timeMax"] = time_max

            result = await asyncio.to_thread(
                lambda: service.events().list(**params).execute()
            )

            events = result.get("items", [])
            formatted = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))
                formatted.append({
                    "id": event["id"],
                    "summary": event.get("summary", "(Sin título)"),
                    "start": start,
                    "end": end,
                    "location": event.get("location", ""),
                    "description": event.get("description", ""),
                    "attendees": [
                        a.get("email") for a in event.get("attendees", [])
                    ],
                    "meet_link": event.get("hangoutLink", ""),
                    "status": event.get("status", ""),
                })

            return {
                "success": True,
                "count": len(formatted),
                "events": formatted,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: str = "",
        location: str = "",
        attendees: Optional[List[str]] = None,
        timezone: str = "America/Mexico_City",
        add_meet: bool = False,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """
        Crea un evento en el calendario.

        Args:
            summary: Título del evento/reunión
            start_datetime: Inicio en ISO 8601 (ej: 2026-03-26T10:00:00)
            end_datetime: Fin en ISO 8601 (ej: 2026-03-26T11:00:00)
            description: Descripción del evento
            location: Ubicación del evento
            attendees: Lista de emails de participantes
            timezone: Zona horaria (default: America/Mexico_City)
            add_meet: Si True, agrega enlace de Google Meet
            calendar_id: ID del calendario
        """
        try:
            service = self._get_service()

            event_body: Dict[str, Any] = {
                "summary": summary,
                "description": description,
                "location": location,
                "start": {
                    "dateTime": start_datetime,
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": end_datetime,
                    "timeZone": timezone,
                },
            }

            if attendees:
                event_body["attendees"] = [{"email": e} for e in attendees]

            if add_meet:
                event_body["conferenceData"] = {
                    "createRequest": {
                        "requestId": f"meet-{datetime.utcnow().timestamp()}",
                        "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    }
                }

            conference_version = 1 if add_meet else 0

            result = await asyncio.to_thread(
                lambda: service.events()
                .insert(
                    calendarId=calendar_id,
                    body=event_body,
                    conferenceDataVersion=conference_version,
                    sendUpdates="all",
                )
                .execute()
            )

            return {
                "success": True,
                "message": f"Evento '{summary}' creado exitosamente",
                "event_id": result["id"],
                "html_link": result.get("htmlLink", ""),
                "meet_link": result.get("hangoutLink", ""),
                "start": result["start"].get("dateTime", result["start"].get("date")),
                "end": result["end"].get("dateTime", result["end"].get("date")),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_datetime: Optional[str] = None,
        end_datetime: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
        timezone: str = "America/Mexico_City",
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Actualiza un evento existente."""
        try:
            service = self._get_service()

            # Obtener evento actual
            existing = await asyncio.to_thread(
                lambda: service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )

            # Actualizar solo campos proporcionados
            if summary is not None:
                existing["summary"] = summary
            if description is not None:
                existing["description"] = description
            if location is not None:
                existing["location"] = location
            if start_datetime is not None:
                existing["start"] = {"dateTime": start_datetime, "timeZone": timezone}
            if end_datetime is not None:
                existing["end"] = {"dateTime": end_datetime, "timeZone": timezone}
            if attendees is not None:
                existing["attendees"] = [{"email": e} for e in attendees]

            result = await asyncio.to_thread(
                lambda: service.events()
                .update(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=existing,
                    sendUpdates="all",
                )
                .execute()
            )

            return {
                "success": True,
                "message": f"Evento '{result.get('summary')}' actualizado",
                "event_id": result["id"],
                "html_link": result.get("htmlLink", ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def delete_event(
        self,
        event_id: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Elimina un evento del calendario."""
        try:
            service = self._get_service()

            await asyncio.to_thread(
                lambda: service.events()
                .delete(
                    calendarId=calendar_id,
                    eventId=event_id,
                    sendUpdates="all",
                )
                .execute()
            )

            return {
                "success": True,
                "message": f"Evento '{event_id}' eliminado exitosamente",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def check_availability(
        self,
        emails: List[str],
        time_min: str,
        time_max: str,
        timezone: str = "America/Mexico_City",
    ) -> Dict[str, Any]:
        """
        Verifica disponibilidad de participantes en un rango de tiempo.

        Args:
            emails: Lista de emails a verificar
            time_min: Inicio del rango (ISO 8601)
            time_max: Fin del rango (ISO 8601)
            timezone: Zona horaria
        """
        try:
            service = self._get_service()

            body = {
                "timeMin": time_min,
                "timeMax": time_max,
                "timeZone": timezone,
                "items": [{"id": email} for email in emails],
            }

            result = await asyncio.to_thread(
                lambda: service.freebusy().query(body=body).execute()
            )

            availability = {}
            for email in emails:
                calendar_info = result["calendars"].get(email, {})
                busy_slots = calendar_info.get("busy", [])
                availability[email] = {
                    "busy_slots": busy_slots,
                    "is_available": len(busy_slots) == 0,
                }

            all_available = all(a["is_available"] for a in availability.values())

            return {
                "success": True,
                "all_available": all_available,
                "time_range": {"start": time_min, "end": time_max},
                "availability": availability,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_calendars(self) -> Dict[str, Any]:
        """Lista todos los calendarios disponibles del usuario."""
        try:
            service = self._get_service()

            result = await asyncio.to_thread(
                lambda: service.calendarList().list().execute()
            )

            calendars = []
            for cal in result.get("items", []):
                calendars.append({
                    "id": cal["id"],
                    "summary": cal.get("summary", ""),
                    "primary": cal.get("primary", False),
                    "timezone": cal.get("timeZone", ""),
                    "access_role": cal.get("accessRole", ""),
                })

            return {
                "success": True,
                "count": len(calendars),
                "calendars": calendars,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
