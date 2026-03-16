"""Script para probar el aislamiento de colecciones ChromaDB por agente."""
import requests
import json
import tempfile
import os

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

def create_temp_file(content, filename):
    """Crea un archivo temporal con contenido."""
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return filepath

def test_collection_isolation():
    """Prueba el aislamiento de colecciones entre agentes."""
    print("\n🔒 PROBANDO AISLAMIENTO DE COLECCIONES CHROMADB")
    
    # 1. Crear dos agentes
    print("\n1️⃣ Creando dos agentes...")
    
    response = requests.post(
        f"{BASE_URL}/agents",
        json={
            "agent_id": "doctor-agent",
            "name": "Doctor Médico",
            "prompt": "Eres un doctor especializado en medicina general. Proporcionas información médica precisa.",
            "description": "Agente médico"
        }
    )
    print_response("Agente Doctor Creado", response)
    
    response = requests.post(
        f"{BASE_URL}/agents",
        json={
            "agent_id": "lawyer-agent",
            "name": "Abogado Legal",
            "prompt": "Eres un abogado experto en derecho. Proporcionas asesoría legal precisa.",
            "description": "Agente legal"
        }
    )
    print_response("Agente Abogado Creado", response)
    
    # 2. Crear documentos temporales con información específica
    print("\n2️⃣ Creando documentos de prueba...")
    
    medical_content = """
    DOCUMENTO MÉDICO CONFIDENCIAL
    
    Tratamiento para dolor de cabeza:
    - Tomar paracetamol 500mg cada 8 horas
    - Descansar en un lugar oscuro y silencioso
    - Mantenerse hidratado
    - Evitar pantallas durante 2 horas
    
    Información de contacto: Dr. Juan Pérez, tel: 555-MEDICINA
    """
    
    legal_content = """
    DOCUMENTO LEGAL CONFIDENCIAL
    
    Proceso para registro de marca:
    - Búsqueda de antecedentes registrales
    - Presentación de solicitud ante la oficina de marcas
    - Publicación en gaceta oficial
    - Obtención del certificado de registro
    
    Información de contacto: Lic. María García, tel: 555-LEGAL
    """
    
    medical_file = create_temp_file(medical_content, "medical_doc.txt")
    legal_file = create_temp_file(legal_content, "legal_doc.txt")
    
    print("✅ Documentos creados:")
    print(f"   • Documento médico: {medical_file}")
    print(f"   • Documento legal: {legal_file}")
    
    # 3. Ingerir documento médico SOLO para doctor-agent
    print("\n3️⃣ Subiendo documento médico al agente doctor...")
    
    with open(medical_file, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/ingest?agent_id=doctor-agent",
            files={"upload": ("medical_doc.txt", f, "text/plain")}
        )
    print_response("Ingesta Médica", response)
    
    # 4. Ingerir documento legal SOLO para lawyer-agent
    print("\n4️⃣ Subiendo documento legal al agente abogado...")
    
    with open(legal_file, 'rb') as f:
        response = requests.post(
            f"{BASE_URL}/ingest?agent_id=lawyer-agent",
            files={"upload": ("legal_doc.txt", f, "text/plain")}
        )
    print_response("Ingesta Legal", response)
    
    # 5. Ver colecciones de agentes
    print("\n5️⃣ Listando colecciones de agentes...")
    response = requests.get(f"{BASE_URL}/chromadb/agents")
    print_response("Colecciones por Agente", response)
    
    # 6. Pregunta médica al doctor (debe responder con info)
    print("\n6️⃣ Preguntando al doctor sobre dolor de cabeza...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "¿Qué debo hacer para el dolor de cabeza?",
            "agent_id": "doctor-agent",
            "session_id": "test-medical",
            "use_rag": True,
            "temperature": 0.1
        }
    )
    print_response("Respuesta Doctor (CON contexto médico)", response)
    
    # 7. Pregunta médica al abogado (NO debe tener info médica)
    print("\n7️⃣ Preguntando al abogado sobre dolor de cabeza...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "¿Qué debo hacer para el dolor de cabeza?",
            "agent_id": "lawyer-agent",
            "session_id": "test-legal",
            "use_rag": True,
            "temperature": 0.1
        }
    )
    print_response("Respuesta Abogado (SIN contexto médico)", response)
    
    # 8. Pregunta legal al abogado (debe responder con info)
    print("\n8️⃣ Preguntando al abogado sobre registro de marca...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "¿Cómo registro una marca?",
            "agent_id": "lawyer-agent",
            "session_id": "test-legal",
            "use_rag": True,
            "temperature": 0.1
        }
    )
    print_response("Respuesta Abogado (CON contexto legal)", response)
    
    # 9. Pregunta legal al doctor (NO debe tener info legal)
    print("\n9️⃣ Preguntando al doctor sobre registro de marca...")
    response = requests.post(
        f"{BASE_URL}/chat",
        json={
            "message": "¿Cómo registro una marca?",
            "agent_id": "doctor-agent",
            "session_id": "test-medical",
            "use_rag": True,
            "temperature": 0.1
        }
    )
    print_response("Respuesta Doctor (SIN contexto legal)", response)
    
    # 10. Ver documentos de cada agente
    print("\n🔟 Verificando documentos de cada agente...")
    
    response = requests.get(f"{BASE_URL}/chromadb/agents/doctor-agent")
    print_response("Info Colección Doctor", response)
    
    response = requests.get(f"{BASE_URL}/chromadb/agents/lawyer-agent")
    print_response("Info Colección Abogado", response)
    
    # Resumen
    print("\n" + "="*70)
    print("✅ PRUEBA DE AISLAMIENTO COMPLETADA")
    print("="*70)
    
    print("\n📊 Resultados Esperados:")
    print("  ✅ Doctor responde con información médica del documento")
    print("  ✅ Doctor NO tiene información legal")
    print("  ✅ Abogado responde con información legal del documento")
    print("  ✅ Abogado NO tiene información médica")
    print("  ✅ Cada agente tiene su propia colección aislada")
    
    print("\n🧹 Limpieza (opcional):")
    print("  curl -X DELETE http://localhost:8000/agents/doctor-agent")
    print("  curl -X DELETE http://localhost:8000/agents/lawyer-agent")
    
    # Limpiar archivos temporales
    try:
        os.remove(medical_file)
        os.remove(legal_file)
        print("\n✅ Archivos temporales eliminados")
    except:
        pass

if __name__ == "__main__":
    try:
        # Verificar que la API está corriendo
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        if response.status_code != 200:
            print("❌ La API no está respondiendo correctamente")
            exit(1)
        
        test_collection_isolation()
        
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
