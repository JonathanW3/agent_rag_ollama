"""Script para probar los endpoints de administración de ChromaDB."""
import requests
import json

BASE_URL = "http://localhost:8000"

def print_response(title, response):
    """Imprime una respuesta formateada."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)
    if response.status_code == 200:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

def test_chromadb_endpoints():
    """Prueba los endpoints de ChromaDB."""
    print("\n🧪 Probando endpoints de ChromaDB...")
    
    # 1. Listar colecciones
    response = requests.get(f"{BASE_URL}/chromadb/collections")
    print_response("Listar Colecciones", response)
    
    # 2. Info de colección kb_store
    response = requests.get(f"{BASE_URL}/chromadb/collections/kb_store")
    print_response("Info de kb_store", response)
    
    # 3. Peek colección (primeros documentos)
    response = requests.get(f"{BASE_URL}/chromadb/collections/kb_store/peek?limit=5")
    print_response("Primeros 5 documentos", response)
    
    print("\n" + "="*60)
    print("✅ Prueba completada")
    print("="*60)
    print("\n💡 Para ver todos los comandos disponibles, revisa EJEMPLOS.md")

if __name__ == "__main__":
    try:
        # Verificar que la API está corriendo
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ La API no está respondiendo correctamente")
            exit(1)
        
        test_chromadb_endpoints()
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: No se puede conectar a la API")
        print("Asegúrate de que la API está corriendo:")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        exit(1)
