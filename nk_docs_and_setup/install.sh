#!/usr/bin/env bash
# NK Hub Generation 1-Click Automated Installer (v1.0.0-Generation)
set -e
export PYTHONDONTWRITEBYTECODE=1
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if [ -n "${1:-}" ]; then
    NK_MODEL_PROFILE="$1"
fi
REQ_PROFILE="$(printf '%s' "${NK_MODEL_PROFILE:-generation}" | tr '[:upper:]' '[:lower:]')"
case "$REQ_PROFILE" in
    generation|carbon|neon|pro|flash|argon|standard) export NK_MODEL_PROFILE="$REQ_PROFILE" ;;
    *) export NK_MODEL_PROFILE="generation" ;;
esac

if [ -n "${BASH_VERSION:-}" ]; then
    eval 'SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"'
else
    echo "[WARN] Esecuzione rilevata senza Bash; attivo fallback POSIX \$0." >&2
    SCRIPT_PATH="$0"
fi
if command -v readlink >/dev/null 2>&1; then
    RESOLVED_PATH="$(readlink -f "$SCRIPT_PATH" 2>/dev/null || printf '%s' "$SCRIPT_PATH")"
else
    RESOLVED_PATH="$SCRIPT_PATH"
fi
SCRIPT_DIR="$(cd "$(dirname "$RESOLVED_PATH")" && pwd)"
if [ -d "$SCRIPT_DIR/../scripts" ]; then
    cd "$SCRIPT_DIR/.."
else
    cd "$SCRIPT_DIR"
fi

echo "========================================================="
echo "Inizializzazione NK Hub Generation (v1.0.0-Generation)"
echo "Profilo: NK_MODEL_PROFILE=$NK_MODEL_PROFILE (supporta generation|carbon|neon|pro|flash|argon|standard; default generation, fallback carbon)"
echo "========================================================="

mkdir -p "../.agents"
if [ ! -f "../.agents/skills.json" ] || [ "$(tr -d ' \n\r\t' < "../.agents/skills.json")" = "{}" ]; then
    printf '{\n  "entries": [\n    {\n      "path": "NK_Hub/.agents/skills"\n    }\n  ]\n}\n' > "../.agents/skills.json"
    echo "[OK] Configurato file manifesto ../.agents/skills.json."
fi
if [ ! -f "../.agents/plugins.json" ] || [ "$(tr -d ' \n\r\t' < "../.agents/plugins.json")" = "{}" ]; then
    printf '{\n  "entries": [\n    {\n      "path": "NK_Hub/.agents/plugins"\n    }\n  ]\n}\n' > "../.agents/plugins.json"
    echo "[OK] Configurato file manifesto ../.agents/plugins.json."
fi
if [ -f "nk_docs_and_setup/root_bridge_AGENTS.md" ]; then
    if [ ! -f "../.agents/AGENTS.md" ] || ! cmp -s "nk_docs_and_setup/root_bridge_AGENTS.md" "../.agents/AGENTS.md"; then
        cp -f "nk_docs_and_setup/root_bridge_AGENTS.md" "../.agents/AGENTS.md"
        echo "[OK] Sincronizzato bridge radice ../.agents/AGENTS.md da root_bridge_AGENTS.md."
    else
        echo "[OK] Bridge radice ../.agents/AGENTS.md allineato."
    fi
fi

if [ -d ".agents" ]; then
    echo "[OK] Cartella .agents/ rilevata (6 Sub-Agenti Nativi, 11 Skill Playbook, facciate CLI scripts/, sottopacchetti _internal/, 7 shard DOM-00..06, NK_MODEL_PROFILE=$NK_MODEL_PROFILE)."
fi

PY_CMD="python"
if ! command -v python >/dev/null 2>&1; then
    PY_CMD="python3"
fi

if [ -f "nk_docs_and_setup/requirements.txt" ]; then
    echo "[INFO] Installazione dipendenze da nk_docs_and_setup/requirements.txt..."
    "$PY_CMD" -B -u -m pip install --disable-pip-version-check -r nk_docs_and_setup/requirements.txt
    echo "[OK] Dipendenze installate con successo."
elif [ -f "requirements.txt" ]; then
    echo "[INFO] Installazione dipendenze da requirements.txt..."
    "$PY_CMD" -B -u -m pip install --disable-pip-version-check -r requirements.txt
    echo "[OK] Dipendenze installate con successo."
fi

if [ -f "scripts/nk_session_bootstrap.py" ]; then
    "$PY_CMD" -B -u scripts/nk_session_bootstrap.py
fi
if [ -f "scripts/nk_registry_indexer.py" ]; then
    "$PY_CMD" -B -u scripts/nk_registry_indexer.py --verify
fi
if [ -f "scripts/rsi_convergence_engine.py" ] && [ -d "tests" ]; then
    echo "[INFO] Esecuzione verifica reale RSI (SSOT: nk_tracking/quality_baseline.json)..."
    "$PY_CMD" -B -u scripts/rsi_convergence_engine.py --verify --strict-verify
elif [ -d "tests" ]; then
    echo "[INFO] Esecuzione verifica reale pytest (SSOT: nk_tracking/quality_baseline.json)..."
    "$PY_CMD" -B -u -m pytest tests -p no:cacheprovider -q
fi
echo "[OK] NK Hub Generation (v1.0.0-Generation) verificato con successo. Scrivi in chat: 'avvia generation' o 'avvia nk hub'"
