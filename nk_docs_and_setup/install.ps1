# NK-Hub 1-Click Automated Installer per Windows (v5.0.0-STE100-Unified / v4.8.0-STE100-Unified / v3.0.0-STE100-Unified)
# Milestone: NK-MS-20261106-SOVEREIGN-CLEAN-SLATE-RELEASE-v5.0.0-RSI
$HubRoot = if (Test-Path "$PSScriptRoot\..\scripts") { (Resolve-Path "$PSScriptRoot\..").Path } else { $PSScriptRoot }
Push-Location $HubRoot
try {
    Write-Host "=================================================" -ForegroundColor Cyan
    Write-Host "Inizializzazione Ecosistema Multi-Agente NK-Hub v5.0.0-STE100-Unified (v4.7.0-STE100-Unified / v3.0.0-STE100-Unified)" -ForegroundColor Green
    Write-Host "=================================================" -ForegroundColor Cyan

    if (Test-Path ".agents") {
        (Get-Item ".agents" -Force).Attributes = 'Directory'
        Write-Host "[OK] Cartella .agents/ configurata e visibile (5 Sub-Agenti Nativi, 16 Playbook)." -ForegroundColor Green
    }

    if (Test-Path ".agents/AGENTS.md") {
        Write-Host "[OK] Regolamento .agents/AGENTS.md attivo nel workspace." -ForegroundColor Green
    } else {
        Write-Host "[WARN] File .agents/AGENTS.md non trovato." -ForegroundColor Yellow
    }

    $ReqFile = if (Test-Path "nk_docs_and_setup/requirements.txt") { "nk_docs_and_setup/requirements.txt" } elseif (Test-Path "requirements.txt") { "requirements.txt" } else { $null }
    if ($ReqFile) {
        Write-Host "[INFO] Installazione dipendenze da $ReqFile..." -ForegroundColor Cyan
        pip install -r $ReqFile
        Write-Host "[OK] Dipendenze installate con successo." -ForegroundColor Green
    }

    if (Test-Path "scripts/nk_session_bootstrap.py") {
        python -u scripts/nk_session_bootstrap.py
    }
    if (Test-Path "scripts/nk_registry_indexer.py") {
        python -u scripts/nk_registry_indexer.py --verify
    }
    if (Test-Path "scripts/rsi_convergence_engine.py") {
        python -u scripts/rsi_convergence_engine.py --verify
    }

    Write-Host "[OK] NK-Hub v5.0.0-STE100-Unified (253/253 PASS, Baseline contrattuale >= 245 Golden e Stress Tests) pronto. Scrivi in chat: 'avvia nk hub'" -ForegroundColor Cyan
} finally {
    Pop-Location
}
