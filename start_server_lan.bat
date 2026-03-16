@echo off
REM Inicia la API FastAPI ligada a la LAN (0.0.0.0)
REM Ajusta el puerto si lo necesitas.
SET HOST=0.0.0.0
SET PORT=8000
SET SESSION_TTL=259200

echo Iniciando servidor en %HOST%:%PORT% ...
if exist .venv\Scripts\uvicorn.exe (
    .venv\Scripts\uvicorn.exe app.main:app --reload --host %HOST% --port %PORT%
) else (
    uvicorn app.main:app --reload --host %HOST% --port %PORT%
)
pause
