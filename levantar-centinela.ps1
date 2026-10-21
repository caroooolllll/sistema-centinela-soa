# ============================================================
#  levantar-centinela.ps1
#  Levanta los 6 servicios de Centinela en ventanas separadas
#  Ejecutar desde la raiz del proyecto:
#    .\levantar-centinela.ps1
# ============================================================

$ROOT = $PSScriptRoot

# --- Helpers de color ---
function Write-Step  { param($msg) Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-OK    { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail  { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Red }
function Write-Warn  { param($msg) Write-Host "  [~~] $msg" -ForegroundColor Yellow }
function Write-Title { param($msg) Write-Host "`n$msg" -ForegroundColor White }

# --- Esperar hasta que un puerto responda ---
function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 15, [string]$Label = "servicio")
    Write-Step "Esperando que $Label arranque en :$Port ..."
    $elapsed = 0
    while ($elapsed -lt $TimeoutSec) {
        $conn = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port `
            -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
        if ($conn.TcpTestSucceeded) {
            Write-OK "$Label listo en :$Port"
            return $true
        }
        Start-Sleep -Seconds 1
        $elapsed++
    }
    Write-Fail "$Label no respondio en :$Port despues de ${TimeoutSec}s"
    return $false
}

# --- Abrir nueva ventana de PowerShell para un servicio ---
function Start-Servicio {
    param([string]$Titulo, [string]$Directorio, [string]$Comando)

    $dir = Join-Path $ROOT $Directorio
    if (-not (Test-Path $dir)) {
        Write-Fail "Directorio no encontrado: $dir"
        return
    }

    $tituloEsc = $Titulo.Replace("'", "''")
    $dirEsc    = $dir.Replace("'", "''")
    $cmd = "`$host.UI.RawUI.WindowTitle = '$tituloEsc'; " +
           "Write-Host '======================================' -ForegroundColor Cyan; " +
           "Write-Host '  $tituloEsc' -ForegroundColor Cyan; " +
           "Write-Host '======================================' -ForegroundColor Cyan; " +
           "Set-Location '$dirEsc'; " +
           "Write-Host ('Directorio: ' + (Get-Location)) -ForegroundColor Gray; " +
           "Write-Host ''; " +
           "$Comando"

    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
    Start-Sleep -Milliseconds 400
}

# ============================================================
#  INICIO
# ============================================================

Clear-Host
Write-Host ""
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host "   CENTINELA -- Iniciando sistema"             -ForegroundColor Cyan
Write-Host "   Privada La Condesa"                         -ForegroundColor Cyan
Write-Host "  =============================================" -ForegroundColor Cyan
Write-Host "  Raiz: $ROOT" -ForegroundColor Gray
Write-Host ""

# --- Verificar .env ---
$envFile = Join-Path $ROOT ".env"
if (-not (Test-Path $envFile)) {
    Write-Fail ".env no encontrado"
    Write-Warn "Copia .env.example a .env y agrega tus credenciales"
    Write-Host ""
    pause
    exit 1
}

$envContent = Get-Content $envFile
$keyLine = $envContent | Where-Object { $_ -match "^ANTHROPIC_API_KEY=.+" }
if ($keyLine) {
    Write-OK "ANTHROPIC_API_KEY configurada"
} else {
    Write-Warn "ANTHROPIC_API_KEY vacia -- el asistente IA no funcionara"
}
Write-Host ""

# ============================================================
#  SERVICIOS
# ============================================================

# [1] Django :9000 -- PRIMERO, es el hub de autenticacion
Write-Title "[1/6] Django -- Auth + IA (:9000)"
Start-Servicio `
    -Titulo     "Centinela | Django :9000 Auth+IA" `
    -Directorio "centinela_identidad\backend_django" `
    -Comando    "python manage.py runserver 0.0.0.0:9000"

# Django debe estar listo antes de que los demas verifiquen tokens
$null = Wait-Port -Port 9000 -TimeoutSec 20 -Label "Django"
Write-Host ""

# [2] Frontend estatico :9300
Write-Title "[2/6] Frontend estatico (:9300)"
Start-Servicio `
    -Titulo     "Centinela | Frontend :9300" `
    -Directorio "centinela_identidad\frontend" `
    -Comando    "python -m http.server 9300 --bind 0.0.0.0"

# [3] Decisiones :9004
# Nota: usa imports relativos, debe correr como modulo desde la raiz del servicio
Write-Title "[3/6] Decisiones / Encuestas (:9004)"
Start-Servicio `
    -Titulo     "Centinela | Decisiones :9004" `
    -Directorio "servicio_decisiones" `
    -Comando    "python -m backend.app"

# [4] SDRI Incidencias :9001
Write-Title "[4/6] SDRI -- Incidencias (:9001)"
Start-Servicio `
    -Titulo     "Centinela | SDRI :9001" `
    -Directorio "Servicio de Reporte de Incidencias" `
    -Comando    "python SDRI.PY"

# [5] Posts / Tablon :9002
Write-Title "[5/6] Posts / Tablon (:9002)"
Start-Servicio `
    -Titulo     "Centinela | Posts :9002" `
    -Directorio "centinela_app\centinela_app\backend" `
    -Comando    "python app.py"

# [6] Chat WebSocket :9003
Write-Title "[6/6] Chat WebSocket (:9003)"
Start-Servicio `
    -Titulo     "Centinela | Chat WS :9003" `
    -Directorio "api\api" `
    -Comando    "python -m uvicorn main:app --host 0.0.0.0 --port 9003 --reload"

# ============================================================
#  VALIDACION FINAL
# ============================================================

Write-Host ""
Write-Host "  Validando todos los servicios en 6 segundos..." -ForegroundColor White
Start-Sleep -Seconds 6
Write-Host ""

$servicios = @(
    [PSCustomObject]@{ Puerto = 9000; Nombre = "Django      :9000  Auth + IA" },
    [PSCustomObject]@{ Puerto = 9300; Nombre = "Frontend    :9300  HTML estatico" },
    [PSCustomObject]@{ Puerto = 9001; Nombre = "SDRI        :9001  Incidencias" },
    [PSCustomObject]@{ Puerto = 9002; Nombre = "Posts       :9002  Tablon vecinal" },
    [PSCustomObject]@{ Puerto = 9003; Nombre = "Chat WS     :9003  WebSocket" },
    [PSCustomObject]@{ Puerto = 9004; Nombre = "Decisiones  :9004  Encuestas" }
)

$todosOK = $true
foreach ($svc in $servicios) {
    $conn = Test-NetConnection -ComputerName 127.0.0.1 -Port $svc.Puerto `
        -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
    if ($conn.TcpTestSucceeded) {
        Write-Host "  [OK] $($svc.Nombre)" -ForegroundColor Green
    } else {
        Write-Host "  [!!] $($svc.Nombre)   <-- no responde" -ForegroundColor Red
        $todosOK = $false
    }
}

Write-Host ""
if ($todosOK) {
    Write-Host "  =============================================" -ForegroundColor Green
    Write-Host "   Sistema listo"                               -ForegroundColor Green
    Write-Host ""                                               -ForegroundColor Green
    Write-Host "   Frontend:   http://localhost:9300"          -ForegroundColor Green
    Write-Host "   API:        http://localhost:9000"          -ForegroundColor Green
    Write-Host "   Chat docs:  http://localhost:9003/docs"     -ForegroundColor Green
    Write-Host "  =============================================" -ForegroundColor Green
} else {
    Write-Host "  =============================================" -ForegroundColor Yellow
    Write-Host "   Algunos servicios no arrancaron."           -ForegroundColor Yellow
    Write-Host "   Revisa las ventanas con [!!] en rojo."      -ForegroundColor Yellow
    Write-Host "  =============================================" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Esta ventana puede cerrarse." -ForegroundColor Gray
Write-Host ""
