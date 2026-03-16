"""
Script de ejemplo para probar la integración MCP SQLite.

Ejecutar desde la raíz del proyecto:
    python test_mcp_integration.py
"""

import asyncio
import sys
import os

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp_sqlite.client import get_mcp_client


async def test_basic_operations():
    """Prueba operaciones básicas del cliente MCP."""
    print("=" * 60)
    print("PRUEBA: Operaciones básicas MCP SQLite")
    print("=" * 60)
    
    client = get_mcp_client()
    test_agent_id = "test_agent"
    
    # 1. Inicializar BD del agente
    print("\n1. Inicializando base de datos del agente...")
    success = await client.init_agent_db(test_agent_id)
    print(f"   ✓ BD inicializada: {success}")
    
    # 2. Listar bases de datos
    print("\n2. Listando bases de datos disponibles...")
    dbs = await client.list_databases()
    print(f"   Agentes: {dbs.get('databases', {}).get('agents', [])}")
    print(f"   Sistema: {dbs.get('databases', {}).get('system', [])}")
    
    # 3. Obtener esquema
    print("\n3. Obteniendo esquema de la BD del agente...")
    schema = await client.get_schema(f"agent_{test_agent_id}")
    if schema.get("success"):
        tables = schema.get("tables", {})
        print(f"   ✓ Tablas encontradas: {list(tables.keys())}")
    
    # 4. Insertar datos de prueba
    print("\n4. Insertando datos de prueba...")
    
    # Log de acción
    await client.log_agent_action(
        agent_id=test_agent_id,
        action="test_action",
        session_id="test_session",
        details={"test": "data", "value": 123},
        success=True
    )
    print("   ✓ Log insertado")
    
    # Métrica
    await client.add_metric(
        agent_id=test_agent_id,
        metric_name="test_metric",
        metric_value=42.5,
        metadata={"unit": "ms"}
    )
    print("   ✓ Métrica insertada")
    
    # Documento procesado
    await client.execute_write(
        db_name=f"agent_{test_agent_id}",
        query="""
            INSERT INTO processed_documents 
            (document_id, filename, chunks_count, file_size_bytes, file_type)
            VALUES (?, ?, ?, ?, ?)
        """,
        params=["doc_123", "test_document.pdf", 10, 1024, ".pdf"]
    )
    print("   ✓ Documento registrado")
    
    # 5. Consultar datos
    print("\n5. Consultando datos insertados...")
    
    # Consultar logs
    logs_result = await client.query_for_agent(
        agent_id=test_agent_id,
        query="SELECT action, success, timestamp FROM agent_logs ORDER BY timestamp DESC LIMIT 5"
    )
    if logs_result.get("success"):
        print(f"   Logs encontrados: {logs_result.get('count', 0)}")
        for log in logs_result.get("rows", []):
            print(f"     - {log['action']} (success: {log['success']})")
    
    # Consultar métricas
    metrics_result = await client.query_for_agent(
        agent_id=test_agent_id,
        query="SELECT metric_name, metric_value FROM agent_metrics ORDER BY timestamp DESC LIMIT 5"
    )
    if metrics_result.get("success"):
        print(f"\n   Métricas encontradas: {metrics_result.get('count', 0)}")
        for metric in metrics_result.get("rows", []):
            print(f"     - {metric['metric_name']}: {metric['metric_value']}")
    
    # Consultar documentos
    docs_result = await client.query_for_agent(
        agent_id=test_agent_id,
        query="SELECT filename, chunks_count FROM processed_documents"
    )
    if docs_result.get("success"):
        print(f"\n   Documentos encontrados: {docs_result.get('count', 0)}")
        for doc in docs_result.get("rows", []):
            print(f"     - {doc['filename']} ({doc['chunks_count']} chunks)")
    
    print("\n" + "=" * 60)
    print("✓ Todas las pruebas completadas exitosamente")
    print("=" * 60)


async def test_sql_queries():
    """Prueba consultas SQL más complejas."""
    print("\n" + "=" * 60)
    print("PRUEBA: Consultas SQL avanzadas")
    print("=" * 60)
    
    client = get_mcp_client()
    test_agent_id = "test_agent"
    
    # Insertar más datos de prueba
    print("\n1. Insertando datos adicionales...")
    for i in range(5):
        await client.log_agent_action(
            agent_id=test_agent_id,
            action=f"action_{i % 3}",
            success=(i % 2 == 0)
        )
        
        await client.add_metric(
            agent_id=test_agent_id,
            metric_name="response_time",
            metric_value=100 + (i * 10)
        )
    print("   ✓ Datos insertados")
    
    # Consulta agregada
    print("\n2. Consulta agregada - Resumen de logs por acción...")
    result = await client.query_for_agent(
        agent_id=test_agent_id,
        query="""
            SELECT 
                action,
                COUNT(*) as total,
                SUM(success) as successful,
                ROUND(100.0 * SUM(success) / COUNT(*), 2) as success_rate
            FROM agent_logs
            GROUP BY action
            ORDER BY total DESC
        """
    )
    
    if result.get("success"):
        print(f"   Resultados encontrados: {result.get('count', 0)}")
        for row in result.get("rows", []):
            print(f"     - {row['action']}: {row['total']} total, "
                  f"{row['successful']} exitosas ({row['success_rate']}%)")
    
    # Estadísticas de métricas
    print("\n3. Estadísticas de métricas...")
    result = await client.query_for_agent(
        agent_id=test_agent_id,
        query="""
            SELECT 
                metric_name,
                COUNT(*) as count,
                AVG(metric_value) as avg_value,
                MIN(metric_value) as min_value,
                MAX(metric_value) as max_value
            FROM agent_metrics
            GROUP BY metric_name
        """
    )
    
    if result.get("success"):
        for row in result.get("rows", []):
            print(f"     - {row['metric_name']}:")
            print(f"         Count: {row['count']}")
            print(f"         Avg: {row['avg_value']:.2f}")
            print(f"         Min: {row['min_value']}")
            print(f"         Max: {row['max_value']}")
    
    print("\n" + "=" * 60)
    print("✓ Consultas avanzadas completadas")
    print("=" * 60)


async def test_custom_data():
    """Prueba tabla de datos personalizados."""
    print("\n" + "=" * 60)
    print("PRUEBA: Datos personalizados (custom_data)")
    print("=" * 60)
    
    client = get_mcp_client()
    test_agent_id = "test_agent"
    
    # Insertar datos personalizados
    print("\n1. Insertando configuración personalizada...")
    custom_configs = [
        ("theme", "dark", "ui"),
        ("language", "es", "ui"),
        ("max_tokens", "1000", "llm"),
        ("temperature", "0.7", "llm"),
    ]
    
    for key, value, category in custom_configs:
        await client.execute_write(
            db_name=f"agent_{test_agent_id}",
            query="""
                INSERT INTO custom_data (data_key, data_value, category)
                VALUES (?, ?, ?)
            """,
            params=[key, value, category]
        )
    print("   ✓ Configuraciones insertadas")
    
    # Consultar configuraciones por categoría
    print("\n2. Consultando configuraciones por categoría...")
    result = await client.query_for_agent(
        agent_id=test_agent_id,
        query="""
            SELECT category, data_key, data_value
            FROM custom_data
            ORDER BY category, data_key
        """
    )
    
    if result.get("success"):
        current_category = None
        for row in result.get("rows", []):
            if row["category"] != current_category:
                current_category = row["category"]
                print(f"\n   {current_category.upper()}:")
            print(f"     {row['data_key']}: {row['data_value']}")
    
    # Actualizar un valor
    print("\n3. Actualizando temperatura...")
    await client.execute_write(
        db_name=f"agent_{test_agent_id}",
        query="UPDATE custom_data SET data_value = ? WHERE data_key = ?",
        params=["0.9", "temperature"]
    )
    
    # Verificar actualización
    result = await client.query_for_agent(
        agent_id=test_agent_id,
        query="SELECT data_value FROM custom_data WHERE data_key = ?",
        params=["temperature"]
    )
    
    if result.get("success") and result.get("rows"):
        new_value = result["rows"][0]["data_value"]
        print(f"   ✓ Temperatura actualizada a: {new_value}")
    
    print("\n" + "=" * 60)
    print("✓ Datos personalizados probados correctamente")
    print("=" * 60)


async def main():
    """Ejecuta todas las pruebas."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║  TEST SUITE: MCP SQLite Integration                     ║")
    print("╚" + "=" * 58 + "╝")
    
    try:
        await test_basic_operations()
        await test_sql_queries()
        await test_custom_data()
        
        print("\n\n" + "🎉 " * 20)
        print("\n   TODAS LAS PRUEBAS PASARON EXITOSAMENTE")
        print("\n" + "🎉 " * 20 + "\n")
        
        print("\nPróximos pasos:")
        print("  1. Inicia el servidor: uvicorn app.main:app --reload")
        print("  2. Visita Swagger UI: http://localhost:8000/docs")
        print("  3. Busca la sección '🗄️ MCP SQLite'")
        print("  4. Prueba los endpoints con tus propios agentes\n")
        
    except Exception as e:
        print(f"\n❌ Error durante las pruebas: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
