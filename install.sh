#!/bin/bash
echo "================================================="
echo "🏛️ Inizializzazione Ecosistema Multi-Agente NK-Hub v1.6.0-VibeEnhanced"
echo "================================================="
if [ -d ".agents" ]; then
    echo "[✅] Cartella .agents/ rilevata."
fi
if [ -f "requirements.txt" ]; then
    echo "[📦] Installazione dipendenze da requirements.txt..."
    pip install -r requirements.txt
    echo "[✅] Dipendenze installate."
fi
echo "[🎉] NK-Hub pronto! Apri Antigravity 2.0 e scrivi in chat: 'Avvia l'NK-Master-Hub'"

