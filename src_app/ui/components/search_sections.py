"""LabNK UI Component: Search Sections (NLP & Parametric).
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""


def render_search_sections() -> str:
    """Genera le sezioni di navigazione a tab, ricerca semantica NLP e filtri parametrici."""
    return """    <!-- Navigation Tabs -->
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('nlp-tab')">🔍 Ricerca NLP & Matching Intelligente</button>
        <button class="tab-btn" onclick="switchTab('parametric-tab')">⚙️ Ricerca Parametrica (Consulenti)</button>
        <button class="tab-btn" onclick="switchTab('calendar-tab')">📅 Scadenzario & Calendario Bandi</button>
        <button class="tab-btn" onclick="switchTab('catalog-tab')">📋 Catalogo Completo Bandi CGM</button>
    </div>

    <!-- 1. TAB RICERCA NLP -->
    <div id="nlp-tab" class="tab-content active">
        <!-- Macro-Category Toggle -->
        <div class="macro-toggle-bar">
            <span class="macro-toggle-label">🎯 Macro-Categoria:</span>
            <button class="macro-btn active" id="macro-btn-all" onclick="setMacroCategory('ALL')">Tutte</button>
            <button class="macro-btn" id="macro-btn-pmi" onclick="setMacroCategory('AGEVOLAZIONE_IMPRESA')">🟢 Agevolazioni PMI</button>
            <button class="macro-btn" id="macro-btn-eu" onclick="setMacroCategory('APPALTO_FORNITURA')">🇪🇺 Appalti & Forniture UE</button>
        </div>

        <!-- Quick Preset Buttons -->
        <div class="presets-container">
            <span class="presets-label">⚡ Query Rapide:</span>
            <button class="preset-btn" onclick="runPreset('Cerco finanziamenti a fondo perduto per una startup a Napoli per sviluppo software AI')">🚀 Startup AI Napoli</button>
            <button class="preset-btn" onclick="runPreset('Voucher digitalizzazione PMI Lombardia acquisto software cybersecurity')">💼 Voucher PMI Lombardia</button>
            <button class="preset-btn" onclick="runPreset('Incentivi per transizione 5.0 ed efficientamento energetico processi produttivi')">⚡ Transizione 5.0 Nazionale</button>
            <button class="preset-btn" onclick="runPreset('Horizon Europe EIC accelerator grant ed equity per startup deep tech')">🇪🇺 Deep Tech Horizon EIC</button>
            <button class="preset-btn" onclick="runPreset('Contributi a fondo perduto per innovazione agricola e agrifood in Sicilia')">🌾 Agrifood Sicilia</button>
            <button class="preset-btn" onclick="runPreset('Finanziamento tasso agevolato per macchinari industria 4.0 e robotica in Emilia-Romagna')">⚙️ Meccanica 4.0 Emilia</button>
            <button class="preset-btn" onclick="runPreset('Bando ISI INAIL per sicurezza sul lavoro e bonifica amianto')">🛡️ Bando ISI INAIL</button>
            <button class="preset-btn" onclick="runPreset('Agevolazioni per artigianato moda e tessile in Toscana')">👗 Moda & Tessile Toscana</button>
        </div>

        <div class="search-box">
            <input type="text" id="nlp-input" class="search-input" placeholder="Es. Cerco finanziamenti a fondo perduto per una startup a Napoli per sviluppo software AI..." oninput="debouncedSearchNLP()" onkeypress="if(event.key==='Enter') filterGrantsNLP()">
            <button class="btn" id="btn-nlp-search" onclick="filterGrantsNLP()">
                <span>Trova Bandi</span>
            </button>
        </div>

        <!-- Intent Analysis Box -->
        <div id="intent-card" class="intent-card">
            <div class="intent-header">
                <div class="intent-title">🧠 Analisi Semantica dell'Intento NLP</div>
                <span class="tag-green">Smart Intent Extractor 1.1</span>
            </div>
            <div class="intent-grid">
                <div class="intent-item">
                    <div class="intent-label">📍 Territorio / NUTS</div>
                    <div id="intent-region" class="intent-val">-</div>
                </div>
                <div class="intent-item">
                    <div class="intent-label">🏷️ Codici ATECO Rilevati</div>
                    <div id="intent-ateco" class="intent-val">-</div>
                </div>
                <div class="intent-item">
                    <div class="intent-label">👥 Beneficiari & Forma</div>
                    <div id="intent-beneficiaries" class="intent-val">-</div>
                </div>
                <div class="intent-item">
                    <div class="intent-label">💰 Agevolazione & Budget</div>
                    <div id="intent-funding" class="intent-val">-</div>
                </div>
                <div class="intent-item" style="grid-column: 1 / -1;">
                    <div class="intent-label">🔑 Parole Chiave Estratte</div>
                    <div id="intent-keywords" class="intent-val">-</div>
                </div>
            </div>
        </div>

        <div id="nlp-spinner" class="loading-spinner">⏳ Elaborazione query e calcolo indice di compatibilità...</div>
        <div id="speed-indicator" class="speed-badge"></div>
        <div id="grants-container-nlp" class="grants-grid"></div>
    </div>

    <!-- 2. TAB RICERCA PARAMETRICA -->
    <div id="parametric-tab" class="tab-content">
        <div class="param-form-grid">
            <div class="form-group">
                <label class="form-label">Codice ATECO</label>
                <input type="text" id="param-ateco" class="search-input" style="min-width: unset;" placeholder="es. 62.01.00">
            </div>
            <div class="form-group">
                <label class="form-label">Regione Target</label>
                <input type="text" id="param-region" class="search-input" style="min-width: unset;" placeholder="es. Campania o Tutte">
            </div>
            <div class="form-group">
                <label class="form-label">Beneficiari</label>
                <select id="param-beneficiary" class="form-select">
                    <option value="">Tutte le tipologie</option>
                    <option value="Startup_Innovative">Startup Innovative</option>
                    <option value="PMI">PMI</option>
                    <option value="Grandi_Imprese">Grandi Imprese</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">Tipo Agevolazione</label>
                <select id="param-aid-type" class="form-select">
                    <option value="">Tutte le agevolazioni</option>
                    <option value="fondo perduto">Fondo perduto</option>
                    <option value="voucher">Voucher</option>
                    <option value="credito">Credito d'imposta</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">% Min. Copertura</label>
                <input type="number" id="param-coverage" class="search-input" style="min-width: unset;" placeholder="es. 50" min="0" max="100">
            </div>
            <div class="form-group">
                <label class="form-label">Ricerca Testo</label>
                <input type="text" id="param-text" class="search-input" style="min-width: unset;" placeholder="Parole chiave...">
            </div>
        </div>

        <div style="display: flex; gap: 10px; margin-bottom: 20px;">
            <button class="btn" onclick="filterGrantsParametric()">Applica Filtri</button>
            <button class="btn btn-secondary" onclick="resetParametricFilters()">Ripristina</button>
        </div>

        <div id="param-spinner" class="loading-spinner">⏳ Filtraggio parametrico in corso...</div>
        <div id="grants-container-param" class="grants-grid"></div>
    </div>

    <!-- 3. TAB SCADENZARIO & CALENDARIO BANDI -->
    <div id="calendar-tab" class="tab-content">
        <div class="calendar-header">
            <div>
                <h3 style="margin: 0; font-size: 18px; color: var(--primary);">📅 Scadenzario Attivo & Calendario Bandi</h3>
                <p style="margin: 4px 0 0 0; font-size: 13px; color: var(--text-muted);">Monitora le scadenze dei bandi e scarica gli alert direttamente nel tuo calendario (.ics).</p>
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button class="btn btn-secondary" id="cal-filter-all" onclick="renderCalendarEvents('ALL')">Tutti i Bandi</button>
                <button class="btn btn-secondary" id="cal-filter-fav" onclick="renderCalendarEvents('FAVORITES')">⭐ Solo Preferiti</button>
                <button class="btn btn-secondary" id="cal-filter-imminent" onclick="renderCalendarEvents('IMMINENT')">⏳ In Scadenza (&lt; 30 gg)</button>
            </div>
        </div>
        <div id="calendar-container" class="calendar-timeline-grid"></div>
    </div>

    <!-- MODAL SIMULATORE FINANZIARIO CONTRIBUTO -->
    <div id="simulator-modal" class="modal-overlay" style="display: none;" onclick="if(event.target===this) closeSimulatorModal()">
        <div class="modal-container">
            <div class="modal-header">
                <h3 style="margin: 0; color: var(--primary);">🧮 Simulatore Finanziario Contributo Bando</h3>
                <button class="modal-close-btn" onclick="closeSimulatorModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div id="sim-bando-title" style="font-weight: 600; margin-bottom: 12px; color: var(--accent);"></div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label class="form-label">Budget di Spesa Preventivato (€)</label>
                    <input type="number" id="sim-budget-input" class="search-input" value="100000" min="1000" step="1000" oninput="recalculateSimulation()">
                </div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label class="form-label">% Intensità Contributo Bando</label>
                    <input type="number" id="sim-perc-input" class="search-input" value="70" min="1" max="100" oninput="recalculateSimulation()">
                </div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label class="form-label">Massimale Finanziabile (€)</label>
                    <input type="number" id="sim-max-input" class="search-input" value="200000" min="1000" step="1000" oninput="recalculateSimulation()">
                </div>
                <div class="form-group" style="margin-bottom: 12px;">
                    <label style="display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer;">
                        <input type="checkbox" id="sim-deminimis-check" onchange="recalculateSimulation()">
                        Regime De Minimis applicabile (Plafond € 300.000 su triennio mobile)
                    </label>
                </div>
                <div class="sim-results-card" style="background: var(--surface); padding: 14px; border-radius: 8px; margin-top: 16px; border: 1px solid var(--border);">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                        <span>Contributo Teorico Lordo:</span>
                        <strong id="sim-res-theor">-</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                        <span>Contributo Netto Effettivo (con Cap):</span>
                        <strong id="sim-res-actual" style="color: var(--accent);">-</strong>
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px;">
                        <span>Quota a Carico Impresa (Cofinanziamento):</span>
                        <strong id="sim-res-cofin">-</strong>
                    </div>
                    <div id="sim-deminimis-warning" style="display: none; margin-top: 8px; font-size: 12px; color: #f59e0b; background: rgba(245, 158, 11, 0.1); padding: 6px 10px; border-radius: 4px;">
                        ⚠️ L'importo supera il plafond massimo De Minimis di € 300.000. Il contributo effettivo è stato plafonato.
                    </div>
                </div>
            </div>
            <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px;">
                <button class="btn btn-secondary" onclick="closeSimulatorModal()">Chiudi</button>
            </div>
        </div>
    </div>"""
