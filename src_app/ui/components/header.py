"""LabNK UI Component: Header.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""


def render_header() -> str:
    """Genera l'intestazione della dashboard con status live e pulsante di sincronizzazione."""
    return """    <div class="header" style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px;">
        <div>
            <h1>🏛️ LabNK — Bandi & Intelligence <span class="badge">v1.1.0 Universal</span></h1>
            <div class="header-meta">
                <span class="live-status"><span class="pulse-dot"></span> Live API Server</span>
                <span class="badge" style="background: rgba(16, 185, 129, 0.15); color: var(--accent); border: 1px solid rgba(16, 185, 129, 0.3);">🛡️ 30+ Fonti Ufficiali Monitorate (Invitalia, MIMIT, 20 Regioni, UE SEDIA)</span>
                <span style="font-size: 12px; color: var(--text-muted);">Protocollo CRV 4.0 | Zero-Mock Engine</span>
            </div>
        </div>
        <div>
            <button class="btn" id="btn-sync-harvest" onclick="triggerSyncHarvest()" style="background: var(--surface); border: 1px solid var(--border); color: var(--text); font-size: 13px;">
                <span>🔄 Sincronizza Fonti dal Web</span>
            </button>
        </div>
    </div>"""
