import re
from fastapi import APIRouter, HTTPException
from ..schemas import SQLQueryRequest, SQLWriteRequest
from ..agents import get_agent
from mcp_sqlite.client import get_mcp_client

router = APIRouter(prefix="/mcp", tags=["🗄️ MCP SQLite"])

# --- SQL Validation helpers ---

# Palabras peligrosas prohibidas en queries de usuario
_SQL_DANGEROUS_PATTERNS = re.compile(
    r"\b(DROP|ALTER|ATTACH|DETACH|PRAGMA|VACUUM|REINDEX|CREATE\s+TRIGGER|LOAD_EXTENSION)\b",
    re.IGNORECASE,
)

# Stacked queries: múltiples statements separados por ;
_SQL_MULTI_STATEMENT = re.compile(r";\s*\S")

# Comentarios SQL que pueden ocultar inyecciones
_SQL_COMMENT_PATTERNS = re.compile(r"(--|/\*)")


def _validate_read_query(sql: str) -> None:
    """Valida que una query sea un SELECT seguro. Lanza HTTPException si no."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped.upper().startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="Solo se permiten consultas SELECT en este endpoint."
        )
    if _SQL_DANGEROUS_PATTERNS.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="La consulta contiene operaciones no permitidas (DROP, ALTER, ATTACH, etc.)."
        )
    if _SQL_MULTI_STATEMENT.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="No se permiten múltiples sentencias SQL en una sola consulta."
        )
    if _SQL_COMMENT_PATTERNS.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="No se permiten comentarios SQL en las consultas."
        )


def _validate_write_query(sql: str) -> None:
    """Valida que una query de escritura sea INSERT/UPDATE/DELETE segura."""
    stripped = sql.strip().rstrip(";").strip()
    first_word = stripped.split()[0].upper() if stripped.split() else ""
    if first_word not in ("INSERT", "UPDATE", "DELETE"):
        raise HTTPException(
            status_code=400,
            detail="Solo se permiten operaciones INSERT, UPDATE o DELETE en este endpoint."
        )
    if _SQL_DANGEROUS_PATTERNS.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="La consulta contiene operaciones no permitidas (DROP, ALTER, ATTACH, etc.)."
        )
    if _SQL_MULTI_STATEMENT.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="No se permiten múltiples sentencias SQL en una sola consulta."
        )
    if _SQL_COMMENT_PATTERNS.search(stripped):
        raise HTTPException(
            status_code=400,
            detail="No se permiten comentarios SQL en las consultas."
        )


@router.get("/databases", summary="Listar bases de datos")
async def list_mcp_databases():
    """Lista todas las bases de datos SQLite disponibles (sistema y agentes)."""
    try:
        mcp_client = get_mcp_client()
        result = await mcp_client.list_databases()
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error listando bases de datos: {str(e)}"
        )


@router.get("/databases/{db_name}/schema", summary="Obtener esquema de BD")
async def get_mcp_schema(db_name: str):
    """Obtiene el esquema completo de una base de datos (tablas y columnas)."""
    try:
        mcp_client = get_mcp_client()
        result = await mcp_client.get_schema(db_name)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo esquema: {str(e)}"
        )


@router.post("/agents/{agent_id}/query", summary="Consultar BD de agente")
async def query_agent_database(agent_id: str, request: SQLQueryRequest):
    """Ejecuta una consulta SELECT en la base de datos del agente especificado."""
    _validate_read_query(request.query)
    try:
        mcp_client = get_mcp_client()

        # Inicializar BD del agente si no existe
        await mcp_client.init_agent_db(agent_id)

        result = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query=request.query,
            params=request.params
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando consulta: {str(e)}"
        )


@router.post("/agents/{agent_id}/write", summary="Escribir en BD de agente")
async def write_agent_database(agent_id: str, request: SQLWriteRequest):
    """Ejecuta una operación de escritura (INSERT, UPDATE, DELETE) en la BD del agente."""
    _validate_write_query(request.query)
    try:
        mcp_client = get_mcp_client()

        # Inicializar BD del agente si no existe
        await mcp_client.init_agent_db(agent_id)

        db_name = f"agent_{agent_id}"
        result = await mcp_client.execute_write(
            db_name=db_name,
            query=request.query,
            params=request.params
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error ejecutando escritura: {str(e)}"
        )


@router.get("/agents/{agent_id}/stats", summary="Estadísticas del agente")
async def get_agent_sql_stats(agent_id: str):
    """Obtiene estadísticas detalladas del agente desde su base de datos SQLite."""
    try:
        mcp_client = get_mcp_client()

        # Inicializar BD si no existe
        await mcp_client.init_agent_db(agent_id)

        # Consultar diferentes métricas
        stats = {}

        # Total de logs
        logs_count = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query="SELECT COUNT(*) as total FROM agent_logs"
        )
        stats["total_logs"] = logs_count.get("rows", [{}])[0].get("total", 0) if logs_count.get("success") else 0

        # Logs por acción
        logs_by_action = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query="""
                SELECT action, COUNT(*) as count
                FROM agent_logs
                GROUP BY action
                ORDER BY count DESC
            """
        )
        stats["logs_by_action"] = logs_by_action.get("rows", []) if logs_by_action.get("success") else []

        # Total de métricas
        metrics_count = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query="SELECT COUNT(*) as total FROM agent_metrics"
        )
        stats["total_metrics"] = metrics_count.get("rows", [{}])[0].get("total", 0) if metrics_count.get("success") else 0

        # Documentos procesados
        docs_count = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query="SELECT COUNT(*) as total FROM processed_documents"
        )
        stats["total_documents"] = docs_count.get("rows", [{}])[0].get("total", 0) if docs_count.get("success") else 0

        # Últimas métricas
        recent_metrics = await mcp_client.query_for_agent(
            agent_id=agent_id,
            query="""
                SELECT metric_name, metric_value, timestamp
                FROM agent_metrics
                ORDER BY timestamp DESC
                LIMIT 10
            """
        )
        stats["recent_metrics"] = recent_metrics.get("rows", []) if recent_metrics.get("success") else []

        return {
            "agent_id": agent_id,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo estadísticas: {str(e)}"
        )


@router.post("/agents/{agent_id}/init", summary="Inicializar BD del agente")
async def init_agent_database(agent_id: str):
    """Inicializa la base de datos SQLite para un agente con el esquema completo."""
    try:
        # Verificar que el agente existe
        agent = get_agent(agent_id)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agente '{agent_id}' no encontrado")

        mcp_client = get_mcp_client()
        success = await mcp_client.init_agent_db(agent_id)

        if success:
            return {
                "status": "ok",
                "message": f"Base de datos inicializada para agente '{agent_id}'",
                "agent_id": agent_id,
                "database": f"agent_{agent_id}.db"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Error inicializando base de datos"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error inicializando BD: {str(e)}"
        )
