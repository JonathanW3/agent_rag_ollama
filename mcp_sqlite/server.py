"""
Servidor MCP SQLite

Implementa un servidor MCP que permite ejecutar consultas SQL seguras
sobre bases de datos SQLite.
"""

import sqlite3
import json
from pathlib import Path
from typing import Any, Dict, List
from contextlib import asynccontextmanager

from mcp.server import Server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ListToolsResult,
)


class SQLiteMCPServer:
    """Servidor MCP para consultas SQLite."""
    
    def __init__(self, db_base_path: str = "./mcp_sqlite/databases"):
        self.db_base_path = Path(db_base_path)
        self.db_base_path.mkdir(parents=True, exist_ok=True)
        
        # Crear subdirectorios
        (self.db_base_path / "agents").mkdir(exist_ok=True)
        (self.db_base_path / "system").mkdir(exist_ok=True)
        
        self.server = Server("sqlite-mcp-server")
        self._register_handlers()
    
    def _register_handlers(self):
        """Registra los handlers del servidor MCP."""
        
        @self.server.list_tools()
        async def list_tools() -> ListToolsResult:
            """Lista las herramientas disponibles."""
            return ListToolsResult(
                tools=[
                    Tool(
                        name="query_sqlite",
                        description="Ejecuta una consulta SQL SELECT en una base de datos SQLite. "
                                    "Solo permite consultas de lectura (SELECT).",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "db_name": {
                                    "type": "string",
                                    "description": "Nombre de la base de datos (ej: 'agent_metrics', 'system')"
                                },
                                "query": {
                                    "type": "string",
                                    "description": "Consulta SQL SELECT a ejecutar"
                                },
                                "params": {
                                    "type": "array",
                                    "description": "Parámetros para la consulta (opcional)",
                                    "items": {"type": "string"}
                                }
                            },
                            "required": ["db_name", "query"]
                        }
                    ),
                    Tool(
                        name="get_db_schema",
                        description="Obtiene el esquema de una base de datos SQLite (tablas y columnas).",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "db_name": {
                                    "type": "string",
                                    "description": "Nombre de la base de datos"
                                }
                            },
                            "required": ["db_name"]
                        }
                    ),
                    Tool(
                        name="list_databases",
                        description="Lista todas las bases de datos disponibles.",
                        inputSchema={
                            "type": "object",
                            "properties": {}
                        }
                    ),
                    Tool(
                        name="execute_write",
                        description="Ejecuta una operación de escritura (INSERT, UPDATE, DELETE) en la base de datos. "
                                    "Usar con precaución.",
                        inputSchema={
                            "type": "object",
                            "properties": {
                                "db_name": {
                                    "type": "string",
                                    "description": "Nombre de la base de datos"
                                },
                                "query": {
                                    "type": "string",
                                    "description": "Consulta SQL de escritura"
                                },
                                "params": {
                                    "type": "array",
                                    "description": "Parámetros para la consulta",
                                    "items": {"type": "string"}
                                }
                            },
                            "required": ["db_name", "query"]
                        }
                    )
                ]
            )
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> CallToolResult:
            """Ejecuta una herramienta del servidor."""
            try:
                if name == "query_sqlite":
                    result = await self._query_sqlite(arguments)
                elif name == "get_db_schema":
                    result = await self._get_db_schema(arguments)
                elif name == "list_databases":
                    result = await self._list_databases()
                elif name == "execute_write":
                    result = await self._execute_write(arguments)
                else:
                    result = {"error": f"Herramienta desconocida: {name}"}
                
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps(result, indent=2))]
                )
            except Exception as e:
                return CallToolResult(
                    content=[TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2))],
                    isError=True
                )
    
    def _get_db_path(self, db_name: str) -> Path:
        """Obtiene la ruta completa de una base de datos."""
        # Soportar rutas con subdirectorios (ej: "custom/Monitoring")
        if "/" in db_name:
            custom_path = self.db_base_path / f"{db_name}.db"
            if custom_path.exists():
                return custom_path
            # Si no existe, retornar la ruta para creación
            custom_path.parent.mkdir(parents=True, exist_ok=True)
            return custom_path
        
        # Intentar primero en agents/
        agent_path = self.db_base_path / "agents" / f"{db_name}.db"
        if agent_path.exists():
            return agent_path
        
        # Luego en system/
        system_path = self.db_base_path / "system" / f"{db_name}.db"
        if system_path.exists():
            return system_path
        
        # Si no existe, crear en system por defecto
        return system_path
    
    async def _query_sqlite(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta una consulta SELECT."""
        db_name = arguments["db_name"]
        query = arguments["query"].strip()
        params = arguments.get("params", [])
        
        # Validar que sea una consulta SELECT
        if not query.upper().startswith("SELECT"):
            return {"error": "Solo se permiten consultas SELECT"}
        
        db_path = self._get_db_path(db_name)
        
        if not db_path.exists():
            return {"error": f"Base de datos '{db_name}' no encontrada"}
        
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Convertir a diccionarios
            results = [dict(row) for row in rows]
            
            conn.close()
            
            return {
                "success": True,
                "rows": results,
                "count": len(results),
                "query": query
            }
        except sqlite3.Error as e:
            return {"error": f"Error SQL: {str(e)}"}
    
    async def _get_db_schema(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Obtiene el esquema de la base de datos."""
        db_name = arguments["db_name"]
        db_path = self._get_db_path(db_name)
        
        if not db_path.exists():
            return {"error": f"Base de datos '{db_name}' no encontrada"}
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            # Obtener todas las tablas
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            tables = [row[0] for row in cursor.fetchall()]
            
            schema = {}
            for table in tables:
                # Obtener columnas de cada tabla
                cursor.execute(f"PRAGMA table_info({table})")
                columns = []
                for col in cursor.fetchall():
                    columns.append({
                        "name": col[1],
                        "type": col[2],
                        "notnull": bool(col[3]),
                        "default": col[4],
                        "primary_key": bool(col[5])
                    })
                schema[table] = columns
            
            conn.close()
            
            return {
                "success": True,
                "database": db_name,
                "tables": schema
            }
        except sqlite3.Error as e:
            return {"error": f"Error SQL: {str(e)}"}
    
    async def _list_databases(self) -> Dict[str, Any]:
        """Lista todas las bases de datos disponibles."""
        databases = {
            "agents": [],
            "system": []
        }
        
        # Listar bases de datos en agents/
        agents_dir = self.db_base_path / "agents"
        if agents_dir.exists():
            databases["agents"] = [
                f.stem for f in agents_dir.glob("*.db")
            ]
        
        # Listar bases de datos en system/
        system_dir = self.db_base_path / "system"
        if system_dir.exists():
            databases["system"] = [
                f.stem for f in system_dir.glob("*.db")
            ]
        
        return {
            "success": True,
            "databases": databases
        }
    
    async def _execute_write(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Ejecuta una operación de escritura."""
        db_name = arguments["db_name"]
        query = arguments["query"].strip()
        params = arguments.get("params", [])
        
        db_path = self._get_db_path(db_name)
        
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            
            cursor.execute(query, params)
            conn.commit()
            
            rows_affected = cursor.rowcount
            
            conn.close()
            
            return {
                "success": True,
                "rows_affected": rows_affected,
                "query": query
            }
        except sqlite3.Error as e:
            return {"error": f"Error SQL: {str(e)}"}
    
    def get_server(self) -> Server:
        """Retorna la instancia del servidor MCP."""
        return self.server
