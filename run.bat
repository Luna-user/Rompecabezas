@echo off
REM ==========================================================================
REM  Lanzador rapido del Rompecabezas Fotografico por Gestos
REM  Usa directamente el Python del entorno virtual (.venv), sin activar nada.
REM ==========================================================================
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] No se encontro el entorno virtual .venv
    echo         Crealo con:  py -3.12 -m venv .venv
    echo         e instala:   .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv\Scripts\python.exe" rompecabezas_gestos.py
pause
