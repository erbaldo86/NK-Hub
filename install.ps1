# 🛠️ NK-Hub 1-Click Automated Installer for Windows
Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "🏛️ Inizializzazione Ecosistema Multi-Agente NK-Hub v1.6.0-VibeEnhanced" -ForegroundColor Green
Write-Host "=================================================" -ForegroundColor Cyan

# 1. Unhide .agents folder if it exists
if (Test-Path ".agents") {
    (Get-Item ".agents" -Force).Attributes = 'Directory'
    Write-Host "[✅] Cartella .agents/ configurata e visibile." -ForegroundColor Green
}

# 2. Check and merge AGENTS.md
if (Test-Path ".agents/AGENTS.md") {
    Write-Host "[✅] Regole di governance AGENTS.md attive nel workspace." -ForegroundColor Green
} else {
    Write-Host "[⚠️] Attenzione: File .agents/AGENTS.md non trovato." -ForegroundColor Yellow
}

# 3. Install or verify Python dependencies
if (Test-Path "requirements.txt") {
    Write-Host "[📦] Installazione e verifica dipendenze da requirements.txt..." -ForegroundColor Cyan
    if (Test-Path ".venv/Scripts/pip.exe") {
        & ".\.venv\Scripts\pip.exe" install -r requirements.txt
    } else {
        pip install -r requirements.txt
    }
    Write-Host "[✅] Dipendenze verificate con successo." -ForegroundColor Green
}

Write-Host "[🎉] NK-Hub pronto! Apri Antigravity 2.0 e scrivi in chat: 'Avvia l'NK-Master-Hub'" -ForegroundColor Cyan

