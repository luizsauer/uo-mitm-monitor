@echo off
title UO MITM Monitor
echo [1/3] Verificando dependencias...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERRO] Falha ao instalar dependencias. Verifique se o Python esta no PATH.
    pause
    exit /b
)
echo [2/3] Iniciando Servidor Web...
echo O Dashboard estara disponivel em: http://localhost:5000
echo.
python uo_mitm_web.py
pause
