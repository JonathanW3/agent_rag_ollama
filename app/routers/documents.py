import os
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from ..config import settings
from ..rag.ingest import ingest_file
from ..agents import agent_exists

router = APIRouter(tags=["📄 Documentos"])


@router.post("/ingest", summary="Cargar documento a un agente")
async def ingest(
    upload: UploadFile = File(...),
    agent_id: str = Query(..., description="ID del agente al que asignar el documento"),
    document_title: str = Query(..., description="Título descriptivo del documento"),
    document_version: str = Query(default="1.0", description="Versión del documento (ej: 1.0, v2.3)"),
    country: str = Query(default=None, description="País al que pertenece el documento (ej: Panamá, México)")
):
    """Ingesta un documento (PDF, TXT, JSON, XML, CSV) y lo almacena en la colección del agente especificado con metadata."""
    # Verificar que el agente existe
    if not agent_exists(agent_id):
        raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

    # Validar tipo de archivo
    file_ext = os.path.splitext(upload.filename)[1].lower()
    allowed_extensions = {".pdf", ".txt", ".json", ".xml", ".csv"}
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo no soportado. Usa: {', '.join(allowed_extensions)}"
        )

    # Sanitizar filename para evitar path traversal (../../etc/passwd)
    safe_filename = os.path.basename(upload.filename)
    if not safe_filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

    dest_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

    # Verificar que la ruta resultante sigue dentro de UPLOAD_DIR
    abs_upload_dir = os.path.abspath(settings.UPLOAD_DIR)
    abs_dest_path = os.path.abspath(dest_path)
    if not abs_dest_path.startswith(abs_upload_dir):
        raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return await ingest_file(dest_path, agent_id, document_title, document_version, country)
