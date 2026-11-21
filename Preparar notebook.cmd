@echo off
setlocal
cd /d "%~dp0"
set "PILOTO_RESULTADO=1"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" scripts\preparar_notebook.py %*
    goto resultado
)
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 scripts\preparar_notebook.py %*
    goto resultado
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" >nul 2>&1
if not errorlevel 1 (
    python scripts\preparar_notebook.py %*
    goto resultado
)
set "PILOTO_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PILOTO_PYTHON%" (
    "%PILOTO_PYTHON%" scripts\preparar_notebook.py %*
    goto resultado
)
echo Instale Python 3.12 ou superior e abra este preparador novamente.
echo Consulte a secao Instalacao do README.md.
goto fim
:resultado
set "PILOTO_RESULTADO=%ERRORLEVEL%"
:fim
if not "%APURACAO_OCULTO%"=="1" pause
exit /b %PILOTO_RESULTADO%
