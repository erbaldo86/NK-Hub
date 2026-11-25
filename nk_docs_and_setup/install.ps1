# NK Hub Generation 1-Click Automated Installer per Windows (v1.0.0-Generation)
param(
    [ValidateSet("", "generation", "carbon", "neon", "pro", "flash", "argon", "standard")]
    [string]$Profile = ""
)

$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if (-not [string]::IsNullOrWhiteSpace($Profile)) {
    $env:NK_MODEL_PROFILE = $Profile.Trim().ToLowerInvariant()
} elseif ([string]::IsNullOrWhiteSpace($env:NK_MODEL_PROFILE)) {
    $env:NK_MODEL_PROFILE = "generation"
} else {
    $env:NK_MODEL_PROFILE = $env:NK_MODEL_PROFILE.Trim().ToLowerInvariant()
}
$ActiveProfile = $env:NK_MODEL_PROFILE
if (@("generation", "carbon", "neon", "pro", "flash", "argon", "standard") -notcontains $ActiveProfile) {
    Write-Host "[WARN] Profilo '$ActiveProfile' non supportato. Uso fallback su 'generation'." -ForegroundColor Yellow
    $ActiveProfile = "generation"
    $env:NK_MODEL_PROFILE = $ActiveProfile
}

$HubRoot = if (Test-Path "$PSScriptRoot\..\scripts") { (Resolve-Path "$PSScriptRoot\..").Path } else { $PSScriptRoot }
Push-Location $HubRoot
try {
    Write-Host "=========================================================" -ForegroundColor Cyan
    Write-Host "Inizializzazione NK Hub Generation (v1.0.0-Generation)" -ForegroundColor Green
    Write-Host "Profilo: NK_MODEL_PROFILE=$ActiveProfile (supporta generation|carbon|neon|pro|flash|argon|standard; default generation, fallback carbon)" -ForegroundColor Cyan
    Write-Host "=========================================================" -ForegroundColor Cyan

    $ParentAgentsDir = Join-Path $HubRoot "..\.agents"
    if (-not (Test-Path $ParentAgentsDir)) {
        New-Item -ItemType Directory -Path $ParentAgentsDir -Force | Out-Null
    }

    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $SkillsJsonPath = Join-Path $ParentAgentsDir "skills.json"
    $SkillsContent = "{`n  `"entries`": [`n    {`n      `"path`": `"NK_Hub/.agents/skills`"`n    }`n  ]`n}`n"
    if (-not (Test-Path $SkillsJsonPath) -or ((Get-Content $SkillsJsonPath -Raw).Trim() -eq "{}")) {
        [System.IO.File]::WriteAllText($SkillsJsonPath, $SkillsContent, $Utf8NoBom)
        Write-Host "[OK] Configurato file manifesto ../.agents/skills.json." -ForegroundColor Green
    }

    $PluginsJsonPath = Join-Path $ParentAgentsDir "plugins.json"
    $PluginsContent = "{`n  `"entries`": [`n    {`n      `"path`": `"NK_Hub/.agents/plugins`"`n    }`n  ]`n}`n"
    if (-not (Test-Path $PluginsJsonPath) -or ((Get-Content $PluginsJsonPath -Raw).Trim() -eq "{}")) {
        [System.IO.File]::WriteAllText($PluginsJsonPath, $PluginsContent, $Utf8NoBom)
        Write-Host "[OK] Configurato file manifesto ../.agents/plugins.json." -ForegroundColor Green
    }

    $RootBridgeDst = Join-Path $ParentAgentsDir "AGENTS.md"
    $RootBridgeSrc = Join-Path $HubRoot "nk_docs_and_setup/root_bridge_AGENTS.md"
    if (Test-Path $RootBridgeSrc) {
        $SrcBridgeText = [System.IO.File]::ReadAllText($RootBridgeSrc, [System.Text.Encoding]::UTF8)
        $DstBridgeText = if (Test-Path $RootBridgeDst) { [System.IO.File]::ReadAllText($RootBridgeDst, [System.Text.Encoding]::UTF8) } else { $null }
        if ($SrcBridgeText -ne $DstBridgeText) {
            [System.IO.File]::WriteAllText($RootBridgeDst, $SrcBridgeText, $Utf8NoBom)
            if ($null -eq $DstBridgeText) {
                Write-Host "[OK] Creato bridge radice ../.agents/AGENTS.md." -ForegroundColor Green
            } else {
                Write-Host "[OK] Sincronizzato bridge radice ../.agents/AGENTS.md da root_bridge_AGENTS.md." -ForegroundColor Green
            }
        } else {
            Write-Host "[OK] Bridge radice ../.agents/AGENTS.md allineato." -ForegroundColor Green
        }
    }

    if (Test-Path ".agents") {
        (Get-Item ".agents" -Force).Attributes = 'Directory'
        Write-Host "[OK] Cartella .agents/ configurata (6 Sub-Agenti Nativi, 11 Skill Playbook, facciate CLI scripts/, sottopacchetti _internal/, 7 shard DOM-00..06)." -ForegroundColor Green
    }

    if (Test-Path ".agents/AGENTS.md") {
        Write-Host "[OK] Regolamento .agents/AGENTS.md attivo nel workspace (NK_MODEL_PROFILE=$ActiveProfile)." -ForegroundColor Green
    } else {
        Write-Host "[WARN] File .agents/AGENTS.md non trovato." -ForegroundColor Yellow
    }

    $ReqFile = if (Test-Path "nk_docs_and_setup/requirements.txt") { "nk_docs_and_setup/requirements.txt" } elseif (Test-Path "requirements.txt") { "requirements.txt" } else { $null }
    if ($ReqFile) {
        Write-Host "[INFO] Installazione dipendenze da $ReqFile..." -ForegroundColor Cyan
        python -B -u -m pip install --disable-pip-version-check -r $ReqFile
        if ($LASTEXITCODE -ne 0) { throw "Installazione dipendenze fallita ($LASTEXITCODE)." }
        Write-Host "[OK] Dipendenze installate con successo." -ForegroundColor Green
    }

    if (Test-Path "scripts/nk_session_bootstrap.py") {
        python -B -u scripts/nk_session_bootstrap.py
        if ($LASTEXITCODE -ne 0) { throw "Bootstrap di sessione fallito ($LASTEXITCODE)." }
    }
    if (Test-Path "scripts/nk_registry_indexer.py") {
        python -B -u scripts/nk_registry_indexer.py --verify
        if ($LASTEXITCODE -ne 0) { throw "Verifica registro fallita ($LASTEXITCODE)." }
    }
    if ((Test-Path "scripts/rsi_convergence_engine.py") -and (Test-Path "tests")) {
        Write-Host "[INFO] Esecuzione verifica reale RSI (SSOT: nk_tracking/quality_baseline.json)..." -ForegroundColor Cyan
        python -B -u scripts/rsi_convergence_engine.py --verify --strict-verify
        if ($LASTEXITCODE -ne 0) { throw "Verifica convergenza RSI fallita ($LASTEXITCODE)." }
    } elseif ((Test-Path "scripts/platform_runner.py") -and (Test-Path "tests")) {
        Write-Host "[INFO] Esecuzione verifica pytest isolata su NVMe (%TEMP%)..." -ForegroundColor Cyan
        python -B -u scripts/platform_runner.py --pytest-isolated
        if ($LASTEXITCODE -ne 0) { throw "Suite pytest isolata fallita ($LASTEXITCODE)." }
    } elseif (Test-Path "tests") {
        Write-Host "[INFO] Esecuzione verifica reale pytest (SSOT: nk_tracking/quality_baseline.json)..." -ForegroundColor Cyan
        python -B -u -m pytest tests -p no:cacheprovider -q
        if ($LASTEXITCODE -ne 0) { throw "Suite pytest fallita ($LASTEXITCODE)." }
    }

    Write-Host "[OK] NK Hub Generation (v1.0.0-Generation) verificato con successo. Scrivi in chat: 'avvia generation' o 'avvia nk hub'" -ForegroundColor Cyan
} finally {
    Pop-Location
}
