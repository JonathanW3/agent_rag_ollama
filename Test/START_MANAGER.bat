@echo off
echo 🤖 RAG Ollama API - Manager Dashboard
echo ================================================
echo.

REM Activar entorno virtual si existe
if exist ".venv\Scripts\activate.bat" (
    echo 📦 Activando entorno virtual...
    call .venv\Scripts\activate.bat
) else (
    echo ⚠️  No se encontró entorno virtual en .venv
    echo    Asegúrate de tener las dependencias instaladas
    echo.
    pause
)

REM Verificar que streamlit esté instalado
python -c "import streamlit" 2>nul
if errorlevel 1 (
    echo ⚠️  Streamlit no está instalado
    echo 📦 Instalando dependencias...
    pip install streamlit requests
    echo ✅ Dependencias instaladas
    echo.
)

echo 💡 Asegúrate de que la API FastAPI esté ejecutándose
echo    URL: http://localhost:8000
echo    Comando: uvicorn app.main:app --reload
echo.
echo 🚀 Iniciando Streamlit Manager Dashboard...
echo.

REM Ejecutar Streamlit
streamlit run Test\app_manager.py

pause
