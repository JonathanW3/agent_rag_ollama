import os
import uuid
import json
import csv
import xml.etree.ElementTree as ET
from datetime import datetime
from pypdf import PdfReader
from .chunking import chunk_text
from .store import get_collection
from ..ollama_client import ollama_embed

# Importar cliente MCP para registrar documentos
try:
    from mcp_sqlite.client import get_mcp_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Tipos de archivo soportados
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".json", ".xml", ".csv"}

def extract_text(path):
    """Extrae texto de diferentes tipos de archivo."""
    ext = os.path.splitext(path)[1].lower()
    
    if ext == ".pdf":
        reader = PdfReader(path)
        return "\n".join([p.extract_text() or "" for p in reader.pages])
    
    elif ext == ".txt":
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    
    elif ext == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            # Convertir JSON a texto legible
            return json.dumps(data, indent=2, ensure_ascii=False)
    
    elif ext == ".xml":
        tree = ET.parse(path)
        root = tree.getroot()
        # Extraer todo el texto del XML
        text_parts = []
        for elem in root.iter():
            if elem.text and elem.text.strip():
                text_parts.append(elem.text.strip())
            if elem.tail and elem.tail.strip():
                text_parts.append(elem.tail.strip())
        return "\n".join(text_parts)
    
    elif ext == ".csv":
        text_parts = []
        with open(path, encoding="utf-8", newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                text_parts.append(", ".join(row))
        return "\n".join(text_parts)
    
    else:
        # Intento de lectura genérica como texto plano
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()

async def ingest_file(path, agent_id: str = "default", document_title: str = None, document_version: str = None, country: str = None):
    """Ingesta un archivo y lo almacena en la colección del agente especificado con metadata completa."""
    text = extract_text(path)
    chunks = chunk_text(text)
    embeddings = ollama_embed(chunks)
    col = get_collection(agent_id)  # Colección específica del agente
    
    # Extraer información del archivo
    filename = os.path.basename(path)
    file_ext = os.path.splitext(path)[1].lower()
    ingested_at = datetime.utcnow().isoformat() + "Z"
    total_chunks = len(chunks)
    
    # Usar título proporcionado o nombre del archivo
    title = document_title if document_title else filename
    version = document_version if document_version else "1.0"
    doc_country = country if country else "N/A"
    
    # Crear metadata para cada chunk
    ids = [str(uuid.uuid4()) for _ in chunks]
    metadatas = [
        {
            "filename": filename,
            "title": title,
            "version": version,
            "country": doc_country,
            "file_type": file_ext,
            "agent_id": agent_id,
            "chunk_index": i,
            "total_chunks": total_chunks,
            "ingested_at": ingested_at,
            "source_path": path
        }
        for i in range(total_chunks)
    ]
    
    # Agregar documentos con metadata
    col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    
    # Registrar documento en SQLite si MCP está disponible
    if MCP_AVAILABLE:
        try:
            mcp_client = get_mcp_client()
            await mcp_client.init_agent_db(agent_id)
            
            # Obtener tamaño del archivo
            file_size = os.path.getsize(path) if os.path.exists(path) else 0
            
            # Registrar documento procesado
            doc_id = str(uuid.uuid4())
            await mcp_client.execute_write(
                db_name=f"agent_{agent_id}",
                query="""
                    INSERT INTO processed_documents 
                    (document_id, filename, chunks_count, file_size_bytes, file_type, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                params=[doc_id, filename, total_chunks, file_size, file_ext, "completed"]
            )
            
            # Registrar métrica de ingesta
            await mcp_client.add_metric(
                agent_id=agent_id,
                metric_name="document_ingested",
                metric_value=total_chunks,
                metadata={"filename": filename, "file_type": file_ext}
            )
        except Exception as e:
            print(f"Error registrando en SQLite: {e}")
            # No fallar la ingesta si SQLite falla
    
    return {
        "status": "ok",
        "chunks": len(chunks),
        "agent_id": agent_id,
        "collection": f"kb_store_{agent_id}",
        "title": title,
        "version": version,
        "country": doc_country,
        "filename": filename
    }
