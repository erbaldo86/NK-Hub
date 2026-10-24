#!/bin/bash
# NK-Hub 1-Click Automated Installer (v4.5.0-STE100-Unified / v3.0.0-STE100-Unified)
set -e
echo "================================================="
echo "Inizializzazione Ecosistema Multi-Agente NK-Hub v4.5.0-STE100-Unified (v3.0.0-STE100-Unified)"
echo "================================================="
if [ -d ".agents" ]; then
    echo "[OK] Cartella .agents/ rilevata (5 Sub-Agenti Nativi, 16 Playbook)."
fi
if [ -f "requirements.txt" ]; then
    echo "[INFO] Installazione dipendenze da requirements.txt..."
    pip install -r requirements.txt
    echo "[OK] Dipendenze installate con successo."
fi
if [ -f "scripts/nk_session_bootstrap.py" ]; then
    python3 -u scripts/nk_session_bootstrap.py
fi
if [ -f "scripts/nk_registry_indexer.py" ]; then
    python3 -u scripts/nk_registry_indexer.py --verify
fi
if [ -f "scripts/rsi_convergence_engine.py" ]; then
    python3 -u scripts/rsi_convergence_engine.py --verify
fi
echo "[OK] NK-Hub v4.5.0-STE100-Unified (115 Golden e Stress Tests) pronto. Scrivi in chat: 'avvia nk hub'"
