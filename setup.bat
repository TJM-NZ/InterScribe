@echo off
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$d='%~dp0'; $s=(Get-Content -LiteralPath '%~f0' -Raw) -replace '(?s)\A([^\n]*\n){4}',''; Invoke-Expression $s"
exit /b %errorlevel%

$ErrorActionPreference = 'Stop'
Set-Location $d

Write-Host ""
Write-Host "InterScribe setup (Windows)"
Write-Host "────────────────────────────────"
Write-Host ""

# ── Docker check ─────────────────────────────────────────────────────────────
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker not found. Install Docker Desktop from:"
    Write-Host "  https://www.docker.com/products/docker-desktop/"
    Write-Host "Then re-run this script."
    Read-Host "Press Enter to exit"
    exit 1
}

docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker is not running. Start Docker Desktop and re-run."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "Docker: OK"

# ── Ollama check / install ────────────────────────────────────────────────────
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "Ollama not found. Installing via winget..."
    winget install Ollama.Ollama --silent
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget install failed. Download and install Ollama from https://ollama.com then re-run."
        Read-Host "Press Enter to exit"
        exit 1
    }
    $env:PATH = "$env:LOCALAPPDATA\Programs\Ollama;$env:PATH"
    Write-Host "Ollama installed."
} else {
    Write-Host "Ollama: OK"
}

# ── Start Ollama if not already running ──────────────────────────────────────
$ollamaUp = $false
try {
    Invoke-WebRequest -Uri 'http://localhost:11434' -UseBasicParsing -TimeoutSec 2 | Out-Null
    $ollamaUp = $true
} catch {}

if (-not $ollamaUp) {
    Write-Host "Starting Ollama..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 15; $i++) {
        try {
            Invoke-WebRequest -Uri 'http://localhost:11434' -UseBasicParsing -TimeoutSec 1 | Out-Null
            $ollamaUp = $true
            break
        } catch {
            Start-Sleep 1
        }
    }
    if (-not $ollamaUp) {
        Write-Host "Ollama failed to start. Open a terminal, run 'ollama serve', then re-run this script."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "Ollama started."
} else {
    Write-Host "Ollama: already running"
}

# ── .env setup ───────────────────────────────────────────────────────────────
if (Test-Path '.env') {
    Write-Host ""
    Write-Host ".env already exists — skipping configuration. Delete it and re-run to reconfigure."
} else {
    if (-not (Test-Path '.env.example')) {
        Write-Host "ERROR: .env.example not found. Run this script from the InterScribe repo folder."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Copy-Item '.env.example' '.env'

    Write-Host ""
    Write-Host "Speaker diarization uses pyannote — a one-time setup on HuggingFace is required."
    Write-Host "  1. Create a free account (or log in): https://huggingface.co/join"
    Write-Host "  2. Accept license: https://huggingface.co/pyannote/speaker-diarization-3.1"
    Write-Host "  3. Accept license: https://huggingface.co/pyannote/segmentation-3.0"
    Write-Host "  4. Generate a read token: https://huggingface.co/settings/tokens"
    Write-Host ""
    Write-Host "The token is used once to download the models during build — it is NOT stored in .env."
    Write-Host ""
    $hfToken = Read-Host "Enter your HuggingFace token"
    $env:HF_TOKEN = $hfToken

    $pg = -join ((48..57) + (97..102) | Get-Random -Count 32 | ForEach-Object { [char]$_ })

    $c = Get-Content '.env' -Raw
    $c = $c.Replace('POSTGRES_PASSWORD=changeme', "POSTGRES_PASSWORD=$pg")
    $c = $c.Replace('DATABASE_URL=postgresql://interscribe:changeme@postgres:5432/interscribe', "DATABASE_URL=postgresql://interscribe:$pg@postgres:5432/interscribe")
    $c = $c.Replace('WHISPER_DEVICE=cuda', 'WHISPER_DEVICE=cpu')
    $c = $c.Replace('WHISPER_COMPUTE_TYPE=float16', 'WHISPER_COMPUTE_TYPE=int8')
    $c = $c.Replace('WHISPER_MODEL_SIZE=large-v2', 'WHISPER_MODEL_SIZE=small')
    $c = $c.Replace('OLLAMA_BASE_URL=http://ollama:11434', 'OLLAMA_BASE_URL=http://host.docker.internal:11434')
    [System.IO.File]::WriteAllText(
        (Join-Path (Get-Location) '.env'),
        $c,
        (New-Object System.Text.UTF8Encoding $false)
    )
    Write-Host ".env written."
}

# ── Build and start containers ────────────────────────────────────────────────
Write-Host ""
Write-Host "Building and starting containers (this may take several minutes on first run)..."
Write-Host "Pyannote models (~150 MB) will be downloaded during build..."
# docker-compose.mac.yml disables the ollama Docker container — on Windows,
# Ollama runs natively (same as Mac) and is reached via host.docker.internal
docker compose -f docker-compose.yml -f docker-compose.mac.yml up --build -d
$env:HF_TOKEN = $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Compose failed. See errors above."
    Read-Host "Press Enter to exit"
    exit 1
}

# ── Pull Qwen model ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Pulling Qwen3.5:9b model (~6 GB) — this may take a while..."
ollama pull qwen3.5:9b

# ── Done ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "────────────────────────────────"
Write-Host "InterScribe is running."
Write-Host ""
Write-Host "  Frontend:  http://localhost:3002"
Write-Host "  API docs:  http://localhost:8002/docs"
Write-Host ""
Write-Host "First transcription will download WhisperX models (~1-4 GB, cached after that)."
Write-Host "────────────────────────────────"
Write-Host ""
Read-Host "Press Enter to exit"
