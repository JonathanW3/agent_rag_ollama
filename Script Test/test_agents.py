"""Script para probar el sistema de múltiples agentes."""
import requests
import json

BASE_URL = "http://localhost:8000"

def print_response(title, response):
    """Imprime una respuesta formateada."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)
    if response.status_code in [200, 201]:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(f"❌ Error {response.status_code}: {response.text}")

def test_agent_system():
    """Prueba completa del sistema de agentes."""
    print("\n🤖 PROBANDO SISTEMA DE MÚLTIPLES AGENTES")
    
    # 1. Listar agentes iniciales (debe existir 'default')
    print("\n1️⃣ Listando agentes existentes...")
    response = requests.get(f"{BASE_URL}/agents")
    print_response("Agentes Iniciales", response)
    
    # 2. Crear agente especializado en Python
    print("\n2️⃣ Creando agente experto en Python...")
    response = requests.post(
        f"{BASE_URL}/agents",
        json={
            "agent_id": "python-expert",
            "name": "Experto en Python",
            "prompt": "Eres un experto en programación Python con 10 años de experiencia. Proporcionas código limpio y bien documentado. Explicas conceptos de manera clara y concisa.",
            "description": "Especialista en desarrollo Python"
        }
    )
    print_response("Nuevo Agente Python", response)
    
    # 3. Crear agente de marketing
    print("\n3️⃣ Creando agente de marketing...")
    response = requests.post(
        f"{BASE_URL}/agents",
        json={
            "agent_id": "marketing-pro",
            "name": "Marketing Expert",
            "prompt": "Eres un experto en marketing digital. Proporcionas estrategias creativas y basadas en datos. Tu comunicación es persuasiva pero honesta.",
            "description": "Especialista en marketing digital"
        }
    )
    print_response("Nuevo Agente Marketing", response)
    
    # 4. Listar todos los agentes
    print("\n4️⃣ Listando todos los agentes...")
    response = requests.get(f"{BASE_URL}/agents")
    print_response("Todos los Agentes", response)
    
    # 5. Chat con agente Python
    print("\n5️⃣ Chateando con agente Python...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "¿Cómo creo una lista por comprensión en Python?",
            "agent_id": "python-expert",
            "session_id": "test-python",
            "use_rag": False
        }
    )
    print_response("Respuesta Python Expert", response)
    
    # 6. Chat con agente Marketing
    print("\n6️⃣ Chateando con agente Marketing...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "¿Qué estrategias recomiendas para redes sociales?",
            "agent_id": "marketing-pro",
            "session_id": "test-marketing",
            "use_rag": False
        }
    )
    print_response("Respuesta Marketing Expert", response)
    
    # 7. Ver detalles y estadísticas del agente Python
    print("\n7️⃣ Viendo estadísticas del agente Python...")
    response = requests.get(f"{BASE_URL}/agents/python-expert")
    print_response("Estadísticas Python Expert", response)
    
    # 8. Listar sesiones
    print("\n8️⃣ Listando todas las sesiones...")
    response = requests.get(f"{BASE_URL}/sessions")
    print_response("Todas las Sesiones", response)
    
    # 9. Ver sesiones del agente Python
    print("\n9️⃣ Listando sesiones del agente Python...")
    response = requests.get(f"{BASE_URL}/sessions?agent_id=python-expert")
    print_response("Sesiones de Python Expert", response)
    
    # 10. Ver historial de sesión
    print("\n🔟 Viendo historial de sesión Python...")
    response = requests.get(f"{BASE_URL}/sessions/python-expert/test-python")
    print_response("Historial de Sesión", response)
    
    # 11. Actualizar agente
    print("\n1️⃣1️⃣ Actualizando descripción del agente Python...")
    response = requests.put(
        f"{BASE_URL}/agents/python-expert",
        json={
            "description": "Senior Python Developer - Especializado en clean code"
        }
    )
    print_response("Agente Actualizado", response)
    
    print("\n" + "="*70)
    print("✅ PRUEBA COMPLETADA")
    print("="*70)
    
    # Información adicional
    print("\n📝 Resumen:")
    print("  • Se crearon 2 agentes especializados")
    print("  • Cada agente tiene su propia personalidad y prompt")
    print("  • Las conversaciones están separadas por agente + sesión")
    print("  • Los agentes pueden tener múltiples sesiones activas")
    print("\n💡 Para limpiar:")
    print("  curl -X DELETE http://localhost:8000/agents/python-expert")
    print("  curl -X DELETE http://localhost:8000/agents/marketing-pro")

if __name__ == "__main__":
    try:
        # Verificar que la API está corriendo
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ La API no está respondiendo correctamente")
            exit(1)
        
        test_agent_system()
        
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: No se puede conectar a la API")
        print("Asegúrate de que la API está corriendo:")
        print("  uvicorn app.main:app --host 0.0.0.0 --port 8000")
        exit(1)
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
