#!/bin/bash
set -e
echo "================================================="
echo "Inizializzazione Ecosistema Multi-Agente NK-Hub v3.0.0-STE100-Unified"
echo "================================================="
if [ -d ".agents" ]; then
    echo "[OK] Cartella .agents/ rilevata."
fi
if [ -f "requirements.txt" ]; then
    echo "[INFO] Installazione dipendenze da requirements.txt..."
    pip install -r requirements.txt
    echo "[OK] Dipendenze installate con successo."
fi
if [ -f "scripts/nk_session_bootstrap.py" ]; then
    python3 -u scripts/nk_session_bootstrap.py
fi
echo "[OK] NK-Hub v3.0.0-STE100-Unified pronto. Scrivi in chat: 'avvia nk hub'"
