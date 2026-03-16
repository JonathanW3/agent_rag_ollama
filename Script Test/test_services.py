"""Script para verificar la conexión a Redis y ChromaDB."""
import sys

def test_redis():
    """Prueba la conexión a Redis."""
    try:
        import redis
        client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        client.ping()
        print("✅ Redis: Conectado correctamente")
        return True
    except Exception as e:
        print(f"❌ Redis: Error de conexión - {e}")
        return False

def test_chromadb():
    """Prueba la conexión a ChromaDB."""
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
        
        client = chromadb.HttpClient(
            host='localhost',
            port=8001,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        # Intenta listar colecciones como prueba
        client.heartbeat()
        print("✅ ChromaDB: Conectado correctamente")
        return True
    except Exception as e:
        print(f"❌ ChromaDB: Error de conexión - {e}")
        return False

if __name__ == "__main__":
    print("Verificando conexiones a servicios...\n")
    
    redis_ok = test_redis()
    chroma_ok = test_chromadb()
    
    print("\n" + "="*50)
    if redis_ok and chroma_ok:
        print("✅ Todos los servicios están funcionando correctamente")
        sys.exit(0)
    else:
        print("❌ Algunos servicios no están disponibles")
        print("\nAsegúrate de ejecutar: docker-compose up -d")
        sys.exit(1)
