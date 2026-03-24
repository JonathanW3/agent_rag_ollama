"""
Cliente MCP SQLite

Cliente para interactuar con el servidor MCP SQLite desde FastAPI.
"""

import json
from typing import Any, Dict, List, Optional
from pathlib import Path


class SQLiteMCPClient:
    """Cliente para interactuar con el servidor MCP SQLite."""
    
    def __init__(self, db_base_path: str = "./mcp_sqlite/databases"):
        """
        Inicializa el cliente MCP SQLite.
        
        Args:
            db_base_path: Ruta base para las bases de datos
        """
        self.db_base_path = Path(db_base_path)
        # Importar el servidor localmente para uso directo
        from .server import SQLiteMCPServer
        self._server = SQLiteMCPServer(db_base_path=str(self.db_base_path))
    
    async def query(
        self, 
        db_name: str, 
        query: str, 
        params: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta una consulta SELECT en la base de datos.
        
        Args:
            db_name: Nombre de la base de datos
            query: Consulta SQL SELECT
            params: Parámetros opcionales para la consulta
            
        Returns:
            Diccionario con los resultados
        """
        arguments = {
            "db_name": db_name,
            "query": query,
            "params": params or []
        }
        
        result = await self._server._query_sqlite(arguments)
        return result
    
    async def get_schema(self, db_name: str) -> Dict[str, Any]:
        """
        Obtiene el esquema de una base de datos.
        
        Args:
            db_name: Nombre de la base de datos
            
        Returns:
            Diccionario con el esquema
        """
        arguments = {"db_name": db_name}
        result = await self._server._get_db_schema(arguments)
        return result
    
    async def list_databases(self) -> Dict[str, Any]:
        """
        Lista todas las bases de datos disponibles.
        
        Returns:
            Diccionario con las bases de datos
        """
        result = await self._server._list_databases()
        return result
    
    async def execute_write(
        self, 
        db_name: str, 
        query: str, 
        params: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta una operación de escritura (INSERT, UPDATE, DELETE).
        
        Args:
            db_name: Nombre de la base de datos
            query: Consulta SQL de escritura
            params: Parámetros opcionales para la consulta
            
        Returns:
            Diccionario con el resultado
        """
        arguments = {
            "db_name": db_name,
            "query": query,
            "params": params or []
        }
        
        result = await self._server._execute_write(arguments)
        return result
    
    async def query_for_agent(
        self,
        agent_id: str,
        query: str,
        params: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta una consulta en la base de datos específica de un agente.
        
        Args:
            agent_id: ID del agente
            query: Consulta SQL
            params: Parámetros opcionales
            
        Returns:
            Resultados de la consulta
        """
        db_name = f"agent_{agent_id}"
        return await self.query(db_name, query, params)
    
    async def query_custom_db(
        self,
        db_path: str,
        query: str,
        params: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Ejecuta una consulta en una base de datos SQLite personalizada.
        
        Args:
            db_path: Ruta a la base de datos (ej: 'Monitoring.db', './data/custom.db')
            query: Consulta SQL
            params: Parámetros opcionales
            
        Returns:
            Resultados de la consulta
        """
        # Extraer solo el nombre del archivo sin extensión
        import os
        db_name = os.path.splitext(os.path.basename(db_path))[0]
        
        # Guardar temporalmente la ruta completa en el servidor
        # El servidor buscará primero en la ruta directa si existe
        try:
            # Intentar con la ruta directa primero
            if os.path.exists(db_path):
                # Si la ruta existe, copiar temporalmente al directorio del servidor
                import shutil
                from pathlib import Path
                
                # Asegurar que existe el directorio custom/
                custom_dir = self.db_base_path / "custom"
                custom_dir.mkdir(exist_ok=True)
                
                dest_path = custom_dir / os.path.basename(db_path)
                if not dest_path.exists() or os.path.getmtime(db_path) > os.path.getmtime(dest_path):
                    shutil.copy2(db_path, dest_path)
                
                # Consultar desde custom/
                db_name = f"custom/{os.path.splitext(os.path.basename(db_path))[0]}"
            
            return await self.query(db_name, query, params)
        except Exception as e:
            return {"error": f"No se pudo acceder a la BD personalizada '{db_path}': {str(e)}"}
    
    async def init_agent_db(self, agent_id: str) -> bool:
        """
        Inicializa la base de datos de un agente con las tablas necesarias.
        
        Args:
            agent_id: ID del agente
            
        Returns:
            True si se inicializó correctamente
        """
        db_name = f"agent_{agent_id}"
        
        # Crear tablas básicas
        queries = [
            # Tabla de logs de agente
            """
            CREATE TABLE IF NOT EXISTS agent_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                session_id TEXT,
                details TEXT,
                success BOOLEAN DEFAULT 1
            )
            """,
            # Tabla de métricas
            """
            CREATE TABLE IF NOT EXISTS agent_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                metadata TEXT
            )
            """,
            # Tabla de documentos procesados
            """
            CREATE TABLE IF NOT EXISTS processed_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                chunks_count INTEGER,
                status TEXT DEFAULT 'completed'
            )
            """,
            # Tabla de configuración del agente
            """
            CREATE TABLE IF NOT EXISTS agent_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Tabla de feedback por mensaje (thumbs up/down)
            """
            CREATE TABLE IF NOT EXISTS message_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                score INTEGER NOT NULL CHECK(score IN (-1, 1)),
                user_message TEXT,
                assistant_message TEXT,
                UNIQUE(session_id, message_index)
            )
            """,
            # Tabla de versiones de prompts
            """
            CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                prompt TEXT NOT NULL,
                version INTEGER NOT NULL,
                change_reason TEXT,
                approved_by TEXT DEFAULT 'system',
                status TEXT DEFAULT 'active' CHECK(status IN ('active', 'replaced', 'rollback'))
            )
            """
        ]
        
        try:
            for query in queries:
                await self.execute_write(db_name, query)
            return True
        except Exception as e:
            print(f"Error inicializando BD del agente {agent_id}: {e}")
            return False
    
    async def log_agent_action(
        self,
        agent_id: str,
        action: str,
        session_id: Optional[str] = None,
        details: Optional[Dict] = None,
        success: bool = True
    ) -> bool:
        """
        Registra una acción del agente en su base de datos.
        
        Args:
            agent_id: ID del agente
            action: Descripción de la acción
            session_id: ID de sesión opcional
            details: Detalles adicionales
            success: Si la acción fue exitosa
            
        Returns:
            True si se registró correctamente
        """
        db_name = f"agent_{agent_id}"
        
        query = """
            INSERT INTO agent_logs (action, session_id, details, success)
            VALUES (?, ?, ?, ?)
        """
        
        params = [
            action,
            session_id,
            json.dumps(details) if details else None,
            1 if success else 0
        ]
        
        try:
            result = await self.execute_write(db_name, query, params)
            return result.get("success", False)
        except Exception as e:
            print(f"Error logging action: {e}")
            return False
    
    async def add_metric(
        self,
        agent_id: str,
        metric_name: str,
        metric_value: float,
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Añade una métrica para el agente.
        
        Args:
            agent_id: ID del agente
            metric_name: Nombre de la métrica
            metric_value: Valor de la métrica
            metadata: Metadatos adicionales
            
        Returns:
            True si se añadió correctamente
        """
        db_name = f"agent_{agent_id}"
        
        query = """
            INSERT INTO agent_metrics (metric_name, metric_value, metadata)
            VALUES (?, ?, ?)
        """
        
        params = [
            metric_name,
            metric_value,
            json.dumps(metadata) if metadata else None
        ]
        
        try:
            result = await self.execute_write(db_name, query, params)
            return result.get("success", False)
        except Exception as e:
            print(f"Error adding metric: {e}")
            return False


# Instancia global del cliente
mcp_client: Optional[SQLiteMCPClient] = None


def get_mcp_client() -> SQLiteMCPClient:
    """Obtiene o crea la instancia global del cliente MCP."""
    global mcp_client
    if mcp_client is None:
        mcp_client = SQLiteMCPClient()
    return mcp_client
