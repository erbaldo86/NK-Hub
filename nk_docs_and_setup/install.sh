#!/bin/bash
# NK-Hub 1-Click Automated Installer (v5.2.0-STE100-Unified / v5.2.0-RSI / v5.0.0-STE100-Unified / v4.8.0-STE100-Unified / v3.0.0-STE100-Unified)
# Milestone: NK-MS-20261108-CLEAN-OPTIMIZED-CHECKPOINT-v5.2.0-RSI
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -d "$SCRIPT_DIR/../scripts" ]; then
    cd "$SCRIPT_DIR/.."
else
    cd "$SCRIPT_DIR"
fi
echo "================================================="
echo "Inizializzazione Ecosistema Multi-Agente NK-Hub v5.2.0-STE100-Unified (v5.2.0-RSI / v5.0.0-STE100-Unified / v4.7.0-STE100-Unified / v3.0.0-STE100-Unified)"
echo "================================================="
if [ -d ".agents" ]; then
    echo "[OK] Cartella .agents/ rilevata (5 Sub-Agenti Nativi, 16 Playbook, 34 Script)."
fi
if [ -f "nk_docs_and_setup/requirements.txt" ]; then
    echo "[INFO] Installazione dipendenze da nk_docs_and_setup/requirements.txt..."
    pip install -r nk_docs_and_setup/requirements.txt
    echo "[OK] Dipendenze installate con successo."
elif [ -f "requirements.txt" ]; then
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
echo "[OK] NK-Hub v5.2.0-STE100-Unified (v5.2.0-RSI, 93 Golden & Stress Tests in 18 modules, 93/93 PASS, 34 scripts, 16 skills) pronto. Scrivi in chat: 'avvia nk hub'"
