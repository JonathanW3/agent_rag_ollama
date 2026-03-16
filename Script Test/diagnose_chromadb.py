"""
Script para diagnosticar problemas de ChromaDB
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
import json

def test_chromadb_connection():
    """Probar conexión a ChromaDB y serialización"""
    print("🔍 Testing ChromaDB Connection...")
    
    # Probar conexión HTTP (Docker)
    try:
        print("\n1️⃣ Testing HTTP Client (Docker)...")
        client = chromadb.HttpClient(
            host="localhost",
            port=8001,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        print("   Connected!")
        
        # Listar colecciones
        print("\n2️⃣ Listing collections...")
        collections = client.list_collections()
        print(f"   Found {len(collections)} collections")
        
        # Intentar serializar
        print("\n3️⃣ Testing serialization...")
        for i, col in enumerate(collections):
            print(f"\n   Collection {i+1}:")
            print(f"   - Type: {type(col)}")
            print(f"   - Has name: {hasattr(col, 'name')}")
            
            if hasattr(col, 'name'):
                name = str(col.name)
                print(f"   - Name: {name}")
                
                # Intentar obtener más información
                try:
                    full_col = client.get_collection(name)
                    count = full_col.count()
                    print(f"   - Count: {count}")
                    
                    # Crear dict serializable
                    col_dict = {
                        "name": name,
                        "count": count
                    }
                    
                    # Probar serialización JSON
                    json_str = json.dumps(col_dict)
                    print(f"   - JSON Serializable: ✅")
                    print(f"   - JSON: {json_str}")
                    
                except Exception as e:
                    print(f"   - Error getting collection: {e}")
            
            # Intentar ver todos los atributos
            print(f"   - Attributes: {dir(col)}")
            
            # Intentar acceder a _type si existe
            if hasattr(col, '_type'):
                print(f"   - Has _type: {col._type}")
        
        print("\n✅ All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_chromadb_connection()
