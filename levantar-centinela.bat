@echo off
chcp 65001 >nul
setlocal

:: ============================================================
::  levantar-centinela.bat
::  Alternativa para sistemas sin politica de ejecucion PS1
::  Ejecutar desde la raiz del proyecto haciendo doble clic
::  o con: levantar-centinela.bat
:: ============================================================

set ROOT=%~dp0
:: Quitar barra final
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%

echo.
echo  =============================================
echo   CENTINELA -- Iniciando sistema
echo   Privada La Condesa
echo  =============================================
echo   Raiz: %ROOT%
echo.

:: ── Servicio 1: Django :9000 (PRIMERO) ──────────────────────
echo  [1/6] Levantando Django :9000 -- Auth + IA ...
start "Centinela | Django :9000" cmd /k "cd /d "%ROOT%\centinela_identidad\backend_django" && python manage.py runserver 0.0.0.0:9000"

:: Esperar a que Django arranque antes de los demas
echo  Esperando 8s para que Django este listo...
timeout /t 8 /nobreak >nul

:: ── Servicio 2: Frontend :9300 ───────────────────────────────
echo  [2/6] Levantando Frontend :9300 ...
start "Centinela | Frontend :9300" cmd /k "cd /d "%ROOT%\centinela_identidad\frontend" && python -m http.server 9300 --bind 0.0.0.0"
timeout /t 1 /nobreak >nul

:: ── Servicio 3: Decisiones :9004 ─────────────────────────────
echo  [3/6] Levantando Decisiones :9004 ...
start "Centinela | Decisiones :9004" cmd /k "cd /d "%ROOT%\servicio_decisiones" && python -m backend.app"
timeout /t 1 /nobreak >nul

:: ── Servicio 4: SDRI Incidencias :9001 ───────────────────────
echo  [4/6] Levantando SDRI Incidencias :9001 ...
start "Centinela | SDRI :9001" cmd /k "cd /d "%ROOT%\Servicio de Reporte de Incidencias" && python SDRI.PY"
timeout /t 1 /nobreak >nul

:: ── Servicio 5: Posts :9002 ──────────────────────────────────
echo  [5/6] Levantando Posts :9002 ...
start "Centinela | Posts :9002" cmd /k "cd /d "%ROOT%\centinela_app\centinela_app\backend" && python app.py"
timeout /t 1 /nobreak >nul

:: ── Servicio 6: Chat WebSocket :9003 ─────────────────────────
echo  [6/6] Levantando Chat WebSocket :9003 ...
start "Centinela | Chat WS :9003" cmd /k "cd /d "%ROOT%\api\api" && python -m uvicorn main:app --host 0.0.0.0 --port 9003 --reload"

:: ── Resultado ─────────────────────────────────────────────────
echo.
echo  Esperando 6s para validar servicios...
timeout /t 6 /nobreak >nul
echo.
echo  =============================================
echo   Validacion de puertos:
echo  =============================================

:: Verificar cada puerto con PowerShell (disponible en Windows 7+)
for %%P in (9000 9300 9001 9002 9003 9004) do (
    powershell -Command "if ((Test-NetConnection 127.0.0.1 -Port %%P -WarningAction SilentlyContinue).TcpTestSucceeded) { Write-Host '  [OK] :%%P activo' -ForegroundColor Green } else { Write-Host '  [!!] :%%P NO responde' -ForegroundColor Red }"
)

echo.
echo  =============================================
echo   Frontend:  http://localhost:9300
echo   API:       http://localhost:9000
echo   Chat docs: http://localhost:9003/docs
echo  =============================================
echo.
echo  Cierra esta ventana cuando quieras.
pause >nul
