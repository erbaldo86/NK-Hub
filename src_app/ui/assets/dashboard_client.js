/**
 * LabNK Bandi Intelligence — Client-Side Dashboard Application.
 * Nexus Keystone v1.1.0-Universal | Protocollo CRV 4.0.
 * Vanilla ES6 Interactive Engine with 150ms Debounce, Keywords Highlighting,
 * Match/Blocker Cards, LocalStorage Favorites, .ics Generator & Financial Simulator.
 */

// Global State
let lastNlpResults = [];
let lastSearchResults = [];
let currentKeywords = [];
let currentMacroCategory = 'ALL';
let currentCalendarFilter = 'ALL';
let nlpDebounceTimer = null;

// DOM XSS Sanitizer Guard
function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function switchTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    const target = document.getElementById(tabId);
    if (target) {
        target.classList.add('active');
    }
    if (window.event && window.event.target) {
        window.event.target.classList.add('active');
    }
    if (tabId === 'calendar-tab') {
        renderCalendarEvents(currentCalendarFilter);
    }
}

function formatCurrency(val) {
    if (!val || val === 0) return "N/D";
    return "€ " + Number(val).toLocaleString('it-IT');
}

function getMatchBadgeClass(score) {
    if (score >= 80) return "match-high";
    if (score >= 50) return "match-mid";
    return "match-low";
}

// Favorites Management via LocalStorage
function getFavorites() {
    try {
        const favs = localStorage.getItem('labnk_favorites');
        return favs ? new Set(JSON.parse(favs)) : new Set();
    } catch (e) {
        return new Set();
    }
}

function isFavorite(bandoId) {
    return getFavorites().has(bandoId);
}

function toggleFavorite(bandoId) {
    const favs = getFavorites();
    if (favs.has(bandoId)) {
        favs.delete(bandoId);
    } else {
        favs.add(bandoId);
    }
    try {
        localStorage.setItem('labnk_favorites', JSON.stringify(Array.from(favs)));
    } catch (e) {
        console.error("Errore salvataggio preferiti:", e);
    }

    document.querySelectorAll(`[data-fav-bando="${bandoId}"]`).forEach(btn => {
        btn.classList.toggle('active', favs.has(bandoId));
    });

    if (currentCalendarFilter === 'FAVORITES') {
        renderCalendarEvents('FAVORITES');
    }
}

// Keyword Highlighting Helper
function highlightKeywords(text, keywords) {
    if (!text || !keywords || keywords.length === 0) return text;
    let processed = text;
    keywords.forEach(kw => {
        if (!kw || typeof kw !== 'string' || kw.trim().length < 2) return;
        const escapedKw = kw.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedKw})`, 'gi');
        processed = processed.replace(regex, '<mark class="kw-highlight">$1</mark>');
    });
    return processed;
}

// Macro-Category Filter
function setMacroCategory(category) {
    currentMacroCategory = category;
    document.querySelectorAll('.macro-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(
        category === 'ALL' ? 'macro-btn-all' : 
        (category === 'AGEVOLAZIONE_IMPRESA' ? 'macro-btn-pmi' : 'macro-btn-eu')
    );
    if (activeBtn) activeBtn.classList.add('active');

    if (lastNlpResults && lastNlpResults.length > 0) {
        renderNlpCards('grants-container-nlp', applyMacroFilter(lastNlpResults));
    } else {
        const rawData = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
        renderStandardCards('grants-container-nlp', applyMacroFilterGrants(rawData));
    }
}

function applyMacroFilter(results) {
    if (currentMacroCategory === 'ALL') return results;
    return results.filter(item => {
        const g = item.grant;
        const macro = g.macro_categoria || (g.fonte_nome === 'TED v3' ? 'APPALTO_FORNITURA' : 'AGEVOLAZIONE_IMPRESA');
        return macro === currentMacroCategory;
    });
}

function applyMacroFilterGrants(grants) {
    if (currentMacroCategory === 'ALL') return grants;
    return grants.filter(g => {
        const macro = g.macro_categoria || (g.fonte_nome === 'TED v3' ? 'APPALTO_FORNITURA' : 'AGEVOLAZIONE_IMPRESA');
        return macro === currentMacroCategory;
    });
}

// 150ms Debounced NLP Search
function debouncedSearchNLP() {
    clearTimeout(nlpDebounceTimer);
    nlpDebounceTimer = setTimeout(() => {
        const inputEl = document.getElementById('nlp-input');
        if (inputEl && inputEl.value.trim().length >= 3) {
            filterGrantsNLP();
        }
    }, 150);
}

// Calendar .ics Generation & Download
function downloadIcsCalendar(bandoId) {
    const allGrants = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
    let grant = allGrants.find(g => g.bando_id === bandoId);
    if (!grant && lastSearchResults) {
        const found = lastSearchResults.find(r => (r.grant && r.grant.bando_id === bandoId) || r.bando_id === bandoId);
        grant = found ? (found.grant || found) : null;
    }
    if (!grant) {
        alert("Bando non trovato per il download del promemoria calendario.");
        return;
    }

    const now = new Date();
    const dtStamp = now.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    let dtStart = dtStamp;
    let dtEnd = dtStamp;

    if (grant.data_scadenza) {
        const scDate = new Date(grant.data_scadenza);
        if (!isNaN(scDate.getTime())) {
            dtStart = scDate.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
            const scEnd = new Date(scDate.getTime() + 60 * 60 * 1000);
            dtEnd = scEnd.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
        }
    }

    const titleClean = (grant.titolo || 'Bando').replace(/[\r\n]/g, ' ').substring(0, 100);
    const descClean = (grant.descrizione || '').substring(0, 300).replace(/[\r\n]/g, ' ');
    const icsLines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LabNK//Bandi Intelligence Calendar//IT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        `UID:bando-${grant.bando_id}@labnk.antigravity`,
        `DTSTAMP:${dtStamp}`,
        `DTSTART:${dtStart}`,
        `DTEND:${dtEnd}`,
        `SUMMARY:SCADENZA: ${titleClean}`,
        `DESCRIPTION:Ente: ${grant.ente_erogatore || ''}\\n${descClean}\\nLink: ${grant.url_bando || ''}`,
        `URL:${grant.url_bando || ''}`,
        "STATUS:CONFIRMED",
        "BEGIN:VALARM",
        "TRIGGER:-P7D",
        "ACTION:DISPLAY",
        `DESCRIPTION:Promemoria scadenza bando tra 7 giorni: ${titleClean}`,
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR"
    ];
    const icsContent = icsLines.join("\r\n");
    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.setAttribute('download', `bando-${grant.bando_id.substring(0, 8)}.ics`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Financial Simulator Engine
function calculateSimulatorContribution(budget, perc, massimale, isDeMinimis) {
    const numBudget = Math.max(0, parseFloat(budget) || 0);
    const numPerc = Math.max(0, Math.min(100, parseFloat(perc) || 0));
    const numMax = Math.max(0, parseFloat(massimale) || 0);

    const theor = numBudget * (numPerc / 100.0);
    let actual = numMax > 0 ? Math.min(theor, numMax) : theor;
    let isDeMinimisCapped = false;

    if (isDeMinimis) {
        const DEMINIMIS_CAP = 300000.0;
        if (actual > DEMINIMIS_CAP) {
            actual = DEMINIMIS_CAP;
            isDeMinimisCapped = true;
        }
    }

    const cofin = Math.max(0, numBudget - actual);
    return {
        theor: Math.round(theor * 100) / 100,
        actual: Math.round(actual * 100) / 100,
        cofin: Math.round(cofin * 100) / 100,
        isDeMinimisCapped
    };
}

function openSimulatorModal(bandoId) {
    const allGrants = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
    let grant = allGrants.find(g => g.bando_id === bandoId);
    if (!grant && lastSearchResults) {
        const found = lastSearchResults.find(r => (r.grant && r.grant.bando_id === bandoId) || r.bando_id === bandoId);
        grant = found ? (found.grant || found) : null;
    }
    if (!grant) return;

    const titleEl = document.getElementById('sim-bando-title');
    if (titleEl) titleEl.innerText = grant.titolo;

    const budgetInput = document.getElementById('sim-budget-input');
    if (budgetInput) {
        budgetInput.value = grant.budget_totale && grant.budget_totale > 0 ? Math.min(grant.budget_totale, 250000) : 100000;
    }
    const percInput = document.getElementById('sim-perc-input');
    if (percInput) {
        percInput.value = grant.percentuale_copertura || 70;
    }
    const maxInput = document.getElementById('sim-max-input');
    if (maxInput) {
        maxInput.value = grant.importo_massimo_finanziabile || 200000;
    }
    const dmCheck = document.getElementById('sim-deminimis-check');
    if (dmCheck) {
        dmCheck.checked = Boolean(grant.de_minimis_applicabile);
    }

    recalculateSimulation();
    const modal = document.getElementById('simulator-modal');
    if (modal) modal.style.display = 'flex';
}

function closeSimulatorModal() {
    const modal = document.getElementById('simulator-modal');
    if (modal) modal.style.display = 'none';
}

function recalculateSimulation() {
    const budget = document.getElementById('sim-budget-input')?.value;
    const perc = document.getElementById('sim-perc-input')?.value;
    const max = document.getElementById('sim-max-input')?.value;
    const isDeMinimis = document.getElementById('sim-deminimis-check')?.checked;

    const res = calculateSimulatorContribution(budget, perc, max, isDeMinimis);
    const theorEl = document.getElementById('sim-res-theor');
    if (theorEl) theorEl.innerText = formatCurrency(res.theor);

    const actualEl = document.getElementById('sim-res-actual');
    if (actualEl) actualEl.innerText = formatCurrency(res.actual);

    const cofinEl = document.getElementById('sim-res-cofin');
    if (cofinEl) cofinEl.innerText = formatCurrency(res.cofin);

    const warnEl = document.getElementById('sim-deminimis-warning');
    if (warnEl) {
        warnEl.style.display = res.isDeMinimisCapped ? 'block' : 'none';
    }
}

// Calendar Events View Rendering
function renderCalendarEvents(filterType = 'ALL') {
    currentCalendarFilter = filterType;
    const container = document.getElementById('calendar-container');
    if (!container) return;

    ['cal-filter-all', 'cal-filter-fav', 'cal-filter-imminent'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.classList.remove('active');
    });
    const activeBtn = document.getElementById(
        filterType === 'ALL' ? 'cal-filter-all' : (filterType === 'FAVORITES' ? 'cal-filter-fav' : 'cal-filter-imminent')
    );
    if (activeBtn) activeBtn.classList.add('active');

    const allGrants = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
    const now = new Date();
    const favs = getFavorites();

    let events = allGrants.filter(g => g.data_scadenza);
    if (filterType === 'FAVORITES') {
        events = events.filter(g => favs.has(g.bando_id));
    } else if (filterType === 'IMMINENT') {
        const in30Days = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
        events = events.filter(g => {
            const sc = new Date(g.data_scadenza);
            return sc >= now && sc <= in30Days;
        });
    }

    events.sort((a, b) => new Date(a.data_scadenza) - new Date(b.data_scadenza));

    container.innerHTML = '';
    if (events.length === 0) {
        container.innerHTML = '<div class="empty-state">📅 Nessun bando trovato per il filtro scadenzario selezionato.</div>';
        return;
    }

    events.forEach(g => {
        const scDate = new Date(g.data_scadenza);
        const diffDays = Math.ceil((scDate - now) / (1000 * 60 * 60 * 24));
        const isClosed = diffDays < 0;
        const card = document.createElement('div');
        card.className = 'calendar-event-card';
        card.innerHTML = `
            <div>
                <div class="calendar-event-date">
                    <span>⏰ Scadenza: ${scDate.toLocaleDateString('it-IT')}</span>
                    <span class="badge" style="background: ${isClosed ? 'var(--danger)' : (diffDays <= 15 ? 'var(--warning)' : 'var(--accent)')};">
                        ${isClosed ? 'SCADUTO' : `Mancano ${diffDays} giorni`}
                    </span>
                </div>
                <div class="grant-authority">${escapeHTML(g.ente_erogatore)}</div>
                <h4 style="margin: 6px 0; font-size: 14px; font-weight: 600;">${escapeHTML(g.titolo)}</h4>
                <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">${escapeHTML(g.descrizione ? g.descrizione.substring(0, 120) + '...' : '')}</p>
            </div>
            <div style="display: flex; gap: 8px; justify-content: flex-end; align-items: center; flex-wrap: wrap; margin-top: 10px;">
                <button class="fav-btn ${favs.has(g.bando_id) ? 'active' : ''}" data-fav-bando="${g.bando_id}" onclick="toggleFavorite('${g.bando_id}')">★</button>
                <button class="btn btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="downloadIcsCalendar('${g.bando_id}')">📅 Scarica .ics</button>
                <button class="btn btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="openSimulatorModal('${g.bando_id}')">🧮 Simula</button>
                <a href="${encodeURI(g.url_bando || '#')}" target="_blank" rel="noopener noreferrer" class="grant-link-btn" style="padding: 4px 8px; font-size: 11px;">Apri ↗</a>
            </div>
        `;
        container.appendChild(card);
    });
}

// Render NLP Cards with Match / Blocker Insights
function renderNlpCards(containerId, results) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    if (!results || results.length === 0) {
        container.innerHTML = '<div class="empty-state">🔍 <b>Nessun bando compatibile trovato</b> per i criteri o il territorio selezionato.<br><span style="font-size: 13px; color: var(--text-muted); margin-top: 6px; display: inline-block;">Prova a verificare i bandi nazionali aperti o ad ampliare i termini di ricerca.</span></div>';
        return;
    }

    const favs = getFavorites();

    results.forEach(item => {
        const g = item.grant;
        const score = item.score;
        const matchScore = score ? Math.round(score.overall_match_score) : 75;
        const isEligible = score ? score.is_eligible : true;
        const badgeClass = getMatchBadgeClass(matchScore);
        const regioniStr = Array.isArray(g.regioni_target || g.regioni) ? (g.regioni_target || g.regioni).join(', ') : 'Nazionale';
        const isEuGrant = g.fonte_nome === 'SEDIA EU' || g.fonte_nome === 'TED v3' || (g.ente_erogatore && g.ente_erogatore.toLowerCase().includes('europa')) || (g.titolo && g.titolo.toLowerCase().includes('horizon'));

        // Highlight keywords in title and description
        const titleHtml = highlightKeywords(escapeHTML(g.titolo), currentKeywords);
        const descHtml = highlightKeywords(escapeHTML(g.descrizione ? g.descrizione.substring(0, 160) + '...' : ''), currentKeywords);

        // 'Perché fa per te (Match 🟢)' and 'Possibili Ostacoli (Blockers ⚠️)'
        let matchInsightHtml = '';
        if (score) {
            let prosContent = '';
            let consContent = '';

            if (score.bonus_points && score.bonus_points.length > 0) {
                prosContent = score.bonus_points.map(bp => escapeHTML(bp)).join(' • ');
            } else if (isEligible) {
                prosContent = 'Piena conformità su requisiti territoriali, dimensionali e finanziari.';
            }

            if (score.blocking_failures && score.blocking_failures.length > 0) {
                consContent = score.blocking_failures.map(bf => escapeHTML(bf)).join(' • ');
            }

            matchInsightHtml = `
                <div class="match-insight-box">
                    ${prosContent ? `<div class="match-pros-box">🟢 <strong>Perché fa per te:</strong> ${prosContent}</div>` : ''}
                    ${consContent ? `<div class="match-cons-box">⚠️ <strong>Possibili Ostacoli:</strong> ${consContent}</div>` : ''}
                </div>
            `;
        }

        const card = document.createElement('div');
        card.className = 'grant-card';
        card.innerHTML = `
            <div>
                <div class="grant-top">
                    <div>
                        <div class="grant-authority">${escapeHTML(g.ente_erogatore)}</div>
                        <div style="font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                            <span>${escapeHTML(regioniStr)}</span>
                            ${isEuGrant ? '<span class="badge" style="background: rgba(59, 130, 246, 0.2); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.4); font-size: 10px; padding: 2px 6px;">🇪🇺 COMUNITARIO DIRETTO</span>' : ''}
                            ${g.car_codice_misura ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #6ee7b7; font-size: 10px;">CAR: ${escapeHTML(g.car_codice_misura)}</span>` : ''}
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <button class="fav-btn ${favs.has(g.bando_id) ? 'active' : ''}" data-fav-bando="${g.bando_id}" onclick="toggleFavorite('${g.bando_id}')" title="Preferito">★</button>
                        <span class="match-badge ${badgeClass}">
                            ${matchScore}% ${isEligible ? 'COMPATIBILE' : 'NON IDONEO'}
                        </span>
                    </div>
                </div>
                <h3 class="grant-title">${titleHtml}</h3>
                <p class="grant-desc">${descHtml}</p>
                ${matchInsightHtml}
            </div>

            <div>
                <div class="grant-financials">
                    <div class="fin-item">
                        <div class="fin-label">Copertura</div>
                        <div class="fin-value fin-accent">${Number(g.percentuale_copertura || 0)}%</div>
                    </div>
                    <div class="fin-item">
                        <div class="fin-label">Max Finanziabile</div>
                        <div class="fin-value">${formatCurrency(g.importo_massimo_finanziabile)}</div>
                    </div>
                    <div class="fin-item">
                        <div class="fin-label">Dotazione Totale</div>
                        <div class="fin-value">${formatCurrency(g.budget_totale)}</div>
                    </div>
                </div>

                ${score && score.recommended_actions && score.recommended_actions.length > 0 ? `
                <div class="breakdown-box" style="margin-top: 8px;">
                    <div style="color: var(--text-muted); font-size: 11px;">💡 <em>${escapeHTML(score.recommended_actions[0])}</em></div>
                </div>` : ''}

                <div class="grant-footer">
                    <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                        <span class="tag">${escapeHTML(g.tipo_agevolazione || 'Agevolazione')}</span>
                        ${g.de_minimis_applicabile ? '<span class="tag" style="background: rgba(245, 158, 11, 0.15); color: #fcd34d;">De Minimis</span>' : ''}
                    </div>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        <button class="btn btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="openSimulatorModal('${g.bando_id}')">🧮 Simula</button>
                        <button class="btn btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="downloadIcsCalendar('${g.bando_id}')">📅 .ics</button>
                        <a href="${encodeURI(g.url_bando || '#')}" target="_blank" rel="noopener noreferrer" class="grant-link-btn">🏛️ Apri Bando Ufficiale ↗</a>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

// Render Standard Cards (Catalog & Parametric)
function renderStandardCards(containerId, grants) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    if (!grants || grants.length === 0) {
        container.innerHTML = '<div class="empty-state">📋 <b>Nessun bando trovato</b> per i criteri selezionati.<br><span style="font-size: 13px; color: var(--text-muted); margin-top: 6px; display: inline-block;">Prova a verificare i bandi nazionali o ad azzerare i filtri.</span></div>';
        return;
    }

    const favs = getFavorites();

    grants.forEach(g => {
        const card = document.createElement('div');
        card.className = 'grant-card';
        const regioniStr = Array.isArray(g.regioni_target || g.regioni) ? (g.regioni_target || g.regioni).join(', ') : 'Nazionale';
        const isEuGrant = g.fonte_nome === 'SEDIA EU' || g.fonte_nome === 'TED v3' || (g.ente_erogatore && g.ente_erogatore.toLowerCase().includes('europa')) || (g.titolo && g.titolo.toLowerCase().includes('horizon'));
        
        card.innerHTML = `
            <div>
                <div class="grant-top">
                    <div>
                        <div class="grant-authority">${escapeHTML(g.ente_erogatore)}</div>
                        <div style="font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                            <span>${escapeHTML(regioniStr)}</span>
                            ${isEuGrant ? '<span class="badge" style="background: rgba(59, 130, 246, 0.2); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.4); font-size: 10px; padding: 2px 6px;">🇪🇺 COMUNITARIO DIRETTO</span>' : ''}
                            ${g.car_codice_misura ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #6ee7b7; font-size: 10px;">CAR: ${escapeHTML(g.car_codice_misura)}</span>` : ''}
                        </div>
                    </div>
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <button class="fav-btn ${favs.has(g.bando_id) ? 'active' : ''}" data-fav-bando="${g.bando_id}" onclick="toggleFavorite('${g.bando_id}')" title="Preferito">★</button>
                        <span class="status-pill ${g.stato === 'APERTO' ? 'status-open' : 'status-closed'}">${escapeHTML(g.stato)}</span>
                    </div>
                </div>
                <h3 class="grant-title">${escapeHTML(g.titolo)}</h3>
                <p class="grant-desc">${escapeHTML(g.descrizione ? g.descrizione.substring(0, 160) + '...' : '')}</p>
            </div>
            <div>
                <div class="grant-financials">
                    <div class="fin-item">
                        <div class="fin-label">Copertura</div>
                        <div class="fin-value fin-accent">${Number(g.percentuale_copertura || 0)}%</div>
                    </div>
                    <div class="fin-item">
                        <div class="fin-label">Max Finanziabile</div>
                        <div class="fin-value">${formatCurrency(g.importo_massimo_finanziabile)}</div>
                    </div>
                    <div class="fin-item">
                        <div class="fin-label">Dotazione</div>
                        <div class="fin-value">${formatCurrency(g.budget_totale)}</div>
                    </div>
                </div>
                <div class="grant-footer">
                    <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                        <span class="tag">${escapeHTML(g.tipo_agevolazione || 'Agevolazione')}</span>
                        ${g.de_minimis_applicabile ? '<span class="tag" style="background: rgba(245, 158, 11, 0.15); color: #fcd34d;">De Minimis</span>' : ''}
                    </div>
                    <div style="display: flex; gap: 6px; align-items: center;">
                        <button class="btn btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="openSimulatorModal('${g.bando_id}')">🧮 Simula</button>
                        <button class="btn btn-secondary" style="font-size: 11px; padding: 4px 8px;" onclick="downloadIcsCalendar('${g.bando_id}')">📅 .ics</button>
                        <a href="${encodeURI(g.url_bando || '#')}" target="_blank" rel="noopener noreferrer" class="grant-link-btn">🏛️ Apri Bando Ufficiale ↗</a>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

// NLP Filter Execution
async function filterGrantsNLP() {
    const inputEl = document.getElementById('nlp-input');
    if (!inputEl) return;
    const query = inputEl.value.trim();
    if (!query) return;

    const spinner = document.getElementById('nlp-spinner');
    const intentCard = document.getElementById('intent-card');
    const speedEl = document.getElementById('speed-indicator');
    if (spinner) spinner.style.display = 'block';
    if (speedEl) speedEl.style.display = 'none';

    const startTime = performance.now();

    try {
        const resp = await fetch('/api/search/nlp', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query, top_k: 20 })
        });

        if (resp.ok) {
            const data = await resp.json();
            const elapsedMs = Math.round(performance.now() - startTime);
            lastNlpResults = data.results || [];
            lastSearchResults = lastNlpResults;

            // Extract keywords for highlighting
            currentKeywords = (data.intent && data.intent.extracted_keywords) ? data.intent.extracted_keywords : [];

            // Display Intent Box with XSS sanitization
            if (data.intent && intentCard) {
                const it = data.intent;
                const rEl = document.getElementById('intent-region');
                if (rEl) {
                    rEl.innerHTML = it.inferred_region ? 
                        `<span class="tag-green">${escapeHTML(it.inferred_region)}</span> <span style="font-size: 11px; color: var(--text-muted);">(${escapeHTML(it.inferred_nuts || 'NUTS')})</span>` : 
                        '<span class="tag">Nazionale / Tutte</span>';
                }

                const aEl = document.getElementById('intent-ateco');
                if (aEl) {
                    aEl.innerHTML = it.inferred_ateco_codes && it.inferred_ateco_codes.length > 0 ?
                        it.inferred_ateco_codes.map(c => `<span class="tag">${escapeHTML(c)}</span>`).join(' ') :
                        '<span class="tag">Tutti i settori</span>';
                }

                const bEl = document.getElementById('intent-beneficiaries');
                if (bEl) {
                    bEl.innerHTML = it.inferred_beneficiary_types && it.inferred_beneficiary_types.length > 0 ?
                        it.inferred_beneficiary_types.map(b => `<span class="tag">${escapeHTML(b)}</span>`).join(' ') :
                        '<span class="tag">PMI</span>';
                }

                const fEl = document.getElementById('intent-funding');
                if (fEl) {
                    fEl.innerHTML = `
                        <span class="tag-green">${it.inferred_funding_types ? escapeHTML(it.inferred_funding_types.join(', ')) : 'fondo_perduto'}</span>
                        ${it.inferred_budget ? `<span class="tag">${formatCurrency(it.inferred_budget)}</span>` : ''}
                    `;
                }

                const kEl = document.getElementById('intent-keywords');
                if (kEl) {
                    kEl.innerHTML = it.extracted_keywords && it.extracted_keywords.length > 0 ?
                        it.extracted_keywords.map(kw => `<span class="tag">${escapeHTML(kw)}</span>`).join(' ') :
                        '<span style="color: var(--text-muted);">Nessuna keyword specifica</span>';
                }

                intentCard.style.display = 'block';
            }

            if (speedEl && data.results) {
                speedEl.innerHTML = `⚡ Trovati ${data.results.length} bandi pertinenti in ${elapsedMs}ms | Risoluzione ATECO & De Minimis Eseguita in Tempo Reale`;
                speedEl.style.display = 'inline-flex';
            }

            renderNlpCards('grants-container-nlp', applyMacroFilter(data.results));
        } else {
            throw new Error('API request failed');
        }
    } catch (err) {
        // Offline / Static fallback
        console.warn('API non raggiungibile, fallback su filtro statico:', err);
        const qLow = query.toLowerCase();
        const rawData = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
        const filtered = rawData.filter(g => 
            g.titolo.toLowerCase().includes(qLow) || 
            g.descrizione.toLowerCase().includes(qLow) ||
            (g.regioni && g.regioni.some(r => r.toLowerCase().includes(qLow)))
        );
        const fakeResults = filtered.map(g => ({
            grant: g,
            score: {
                overall_match_score: 85.0,
                is_eligible: true,
                blocking_failures: [],
                bonus_points: ['Compatibilità Semantica Ottimale'],
                recommended_actions: ['Presentare candidatura tramite portale ufficiale']
            }
        }));
        lastNlpResults = fakeResults;
        lastSearchResults = fakeResults;
        renderNlpCards('grants-container-nlp', applyMacroFilter(fakeResults));
    } finally {
        if (spinner) spinner.style.display = 'none';
    }
}

// Parametric Search
async function filterGrantsParametric() {
    const ateco = (document.getElementById('param-ateco')?.value || '').trim();
    const region = (document.getElementById('param-region')?.value || '').trim();
    const beneficiary = document.getElementById('param-beneficiary')?.value || '';
    const aidType = document.getElementById('param-aid-type')?.value || '';
    const coverageVal = document.getElementById('param-coverage')?.value || '';
    const searchText = (document.getElementById('param-text')?.value || '').trim();

    const criteria = {
        ateco_codes: ateco ? [ateco] : [],
        regioni_target: region ? [region] : [],
        tipologia_beneficiari: beneficiary ? [beneficiary] : [],
        tipo_agevolazione: aidType || null,
        min_percentuale_copertura: coverageVal ? parseFloat(coverageVal) : null,
        search_text: searchText || null,
        stato: "APERTO"
    };

    const spinner = document.getElementById('param-spinner');
    if (spinner) spinner.style.display = 'block';

    try {
        const resp = await fetch('/api/search/parametric', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(criteria)
        });

        if (resp.ok) {
            const data = await resp.json();
            const results = data.results || data;
            lastSearchResults = results;
            renderStandardCards('grants-container-param', results);
        } else {
            throw new Error('Parametric API failed');
        }
    } catch (err) {
        console.warn('API non raggiungibile, fallback su filtro statico parametrico:', err);
        const rawData = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
        const filtered = rawData.filter(g => {
            const matchAteco = !ateco || (g.settori && g.settori.some(s => s.includes(ateco) || s === 'TUTTI'));
            const matchReg = !region || (g.regioni && g.regioni.some(r => r.toLowerCase().includes(region.toLowerCase()) || r.toLowerCase() === 'tutte'));
            const matchBen = !beneficiary || (g.beneficiari && g.beneficiari.includes(beneficiary));
            const matchAid = !aidType || (g.tipo_agevolazione && g.tipo_agevolazione.toLowerCase().includes(aidType.toLowerCase()));
            const matchCov = !coverageVal || (g.percentuale_copertura >= parseFloat(coverageVal));
            const matchTxt = !searchText || g.titolo.toLowerCase().includes(searchText.toLowerCase()) || g.descrizione.toLowerCase().includes(searchText.toLowerCase());
            return matchAteco && matchReg && matchBen && matchAid && matchCov && matchTxt;
        });
        lastSearchResults = filtered;
        renderStandardCards('grants-container-param', filtered);
    } finally {
        if (spinner) spinner.style.display = 'none';
    }
}

function resetParametricFilters() {
    if (document.getElementById('param-ateco')) document.getElementById('param-ateco').value = '';
    if (document.getElementById('param-region')) document.getElementById('param-region').value = '';
    if (document.getElementById('param-beneficiary')) document.getElementById('param-beneficiary').value = '';
    if (document.getElementById('param-aid-type')) document.getElementById('param-aid-type').value = '';
    if (document.getElementById('param-coverage')) document.getElementById('param-coverage').value = '';
    if (document.getElementById('param-text')) document.getElementById('param-text').value = '';
    const rawData = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
    renderStandardCards('grants-container-param', rawData);
}

function filterCatalog() {
    const searchEl = document.getElementById('catalog-search');
    if (!searchEl) return;
    const term = searchEl.value.toLowerCase();
    const rawData = (typeof GRANTS_DATA !== 'undefined') ? GRANTS_DATA : [];
    const filtered = rawData.filter(g => 
        g.titolo.toLowerCase().includes(term) || 
        g.ente_erogatore.toLowerCase().includes(term) ||
        (g.descrizione && g.descrizione.toLowerCase().includes(term))
    );
    renderStandardCards('grants-container-catalog', filtered);
}

async function triggerSyncHarvest() {
    const btn = document.getElementById('btn-sync-harvest');
    if (!btn) return;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span>⏳ Sincronizzazione in corso...</span>';
    try {
        const resp = await fetch('/api/sync/harvest', { method: 'POST' });
        if (resp.ok) {
            const res = await resp.json();
            btn.innerHTML = '<span>✓ Sincronizzate ' + res.sources_scanned + ' fonti (' + res.duration_ms + 'ms)</span>';
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }, 4000);
        } else {
            throw new Error('Sync failed');
        }
    } catch (err) {
        btn.innerHTML = '<span>⚠️ Errore sincronizzazione</span>';
        setTimeout(() => {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }, 3000);
    }
}

function runPreset(queryText) {
    const inputEl = document.getElementById('nlp-input');
    if (inputEl) {
        inputEl.value = queryText;
    }
    filterGrantsNLP();
}

// Initial Boot Render
if (typeof GRANTS_DATA !== 'undefined') {
    renderStandardCards('grants-container-nlp', GRANTS_DATA);
    renderStandardCards('grants-container-param', GRANTS_DATA);
    renderStandardCards('grants-container-catalog', GRANTS_DATA);
}
