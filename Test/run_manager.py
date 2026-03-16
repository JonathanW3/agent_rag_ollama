"""
Script de inicio rápido para la aplicación Streamlit Manager
"""

import subprocess
import sys
import os

def check_streamlit():
    """Verifica si Streamlit está instalado."""
    try:
        import streamlit
        return True
    except ImportError:
        return False

def install_dependencies():
    """Instala las dependencias necesarias."""
    print("📦 Instalando dependencias...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "Test/requirements.txt"])
    print("✅ Dependencias instaladas")

def run_streamlit():
    """Ejecuta la aplicación Streamlit."""
    print("🚀 Iniciando Streamlit Manager Dashboard...")
    subprocess.run(["streamlit", "run", "Test/app_manager.py"])

if __name__ == "__main__":
    print("🤖 RAG Ollama API - Manager Dashboard")
    print("=" * 50)
    
    # Verificar si Streamlit está instalado
    if not check_streamlit():
        print("⚠️  Streamlit no está instalado")
        response = input("¿Deseas instalarlo ahora? (s/n): ")
        if response.lower() in ["s", "si", "yes", "y"]:
            install_dependencies()
        else:
            print("❌ No se puede continuar sin Streamlit")
            sys.exit(1)
    
    print("\n💡 Asegúrate de que la API FastAPI esté ejecutándose en http://localhost:8000")
    print("   Puedes iniciarla con: uvicorn app.main:app --reload\n")
    
    input("Presiona ENTER para continuar...")
    
    # Ejecutar Streamlit
    run_streamlit()
