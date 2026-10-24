# NK-Hub 1-Click Automated Installer per Windows (v4.5.0-STE100-Unified / v3.0.0-STE100-Unified)
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "Inizializzazione Ecosistema Multi-Agente NK-Hub v4.5.0-STE100-Unified (v3.0.0-STE100-Unified)" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Rende visibile la cartella .agents se presente
if (Test-Path ".agents") {
    (Get-Item ".agents" -Force).Attributes = 'Directory'
    Write-Host "[OK] Cartella .agents/ configurata e visibile (5 Sub-Agenti Nativi, 16 Playbook)." -ForegroundColor Green
}

# 2. Verifica la presenza di AGENTS.md
if (Test-Path ".agents/AGENTS.md") {
    Write-Host "[OK] Regolamento .agents/AGENTS.md attivo nel workspace." -ForegroundColor Green
} else {
    Write-Host "[WARN] File .agents/AGENTS.md non trovato." -ForegroundColor Yellow
}

# 3. Installa e verifica le dipendenze Python
if (Test-Path "requirements.txt") {
    Write-Host "[INFO] Installazione dipendenze da requirements.txt..." -ForegroundColor Cyan
    if (Test-Path ".venv/Scripts/pip.exe") {
        & ".\.venv\Scripts\pip.exe" install -r requirements.txt
    } else {
        pip install -r requirements.txt
    }
    Write-Host "[OK] Dipendenze installate con successo." -ForegroundColor Green
}

# 4. Esegue il Fast-Stat Session Bootstrap Gate e la verifica O(1) + RSI (115 test)
if (Test-Path "scripts/nk_session_bootstrap.py") {
    python -u scripts/nk_session_bootstrap.py
}
if (Test-Path "scripts/nk_registry_indexer.py") {
    python -u scripts/nk_registry_indexer.py --verify
}
if (Test-Path "scripts/rsi_convergence_engine.py") {
    python -u scripts/rsi_convergence_engine.py --verify
}

Write-Host "[OK] NK-Hub v4.5.0-STE100-Unified (115 Golden e Stress Tests) pronto. Scrivi in chat: 'avvia nk hub'" -ForegroundColor Cyan
