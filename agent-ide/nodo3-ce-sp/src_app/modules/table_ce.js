// 🏛️ TABLE CE CONTROLLER & RENDERER - NODO 3 (ES6 Module)
// Conto Economico Art. 2425 C.C. | Event Delegation Permanente & Sparse Bounded Horizon

import { getState, getTimelineYears, ensureYearRecord } from './state.js';
import { formatEuro, MAX_VISIBLE_YEARS } from './constants.js';
import { recalculateFinancials } from './financial_engine.js';
import { renderSPTables } from './table_sp.js';
import { renderKpiCards, renderCharts } from './kpi_analytics.js';
import { showToast, triggerTableFlash } from './modals.js';

export function getLineageInfo(section, fieldName, yearIndex) {
  const state = getState();
  const overrideKey = `${section}_${fieldName}_${yearIndex}`;
  const isOverride = !!(state.manualOverrides && state.manualOverrides[overrideKey]);

  if (isOverride) {
    return {
      file: 'Utente (Manual Override)',
      path: 'Modifica Manuale in Tabella (Doppio Clic)',
      type: 'Override Manuale Utente ✏️'
    };
  }

  if (state.hitlMappings && state.hitlMappings[fieldName]) {
    const hitl = state.hitlMappings[fieldName];
    return {
      file: hitl.file || (state.uploadedFiles && state.uploadedFiles[0]) || 'Limbo Queue',
      path: hitl.path || 'Revisione Guidata Limbo Queue (HITL)',
      type: 'Mappatura Limbo HITL 🤖'
    };
  }

  if (state.isDocumentLoaded && state.uploadedFiles && state.uploadedFiles.length > 0) {
    const file = state.uploadedFiles[0];
    const details = (state.uploadedFilesDetails && state.uploadedFilesDetails[0]) || {};
    return {
      file: file,
      path: details.sheetName || 'Conto Economico (ODS/XLSX/PDF)',
      type: 'Estrazione Automatica NLP/FastAPI 📄'
    };
  }

  return {
    file: 'Sistema Demo / Previsionale',
    path: 'Algoritmo Previsionale Modello Economico',
    type: 'Dati Benchmark Calcolati 📊'
  };
}

export function renderCETable() {
  const tbody = document.getElementById('ceTableBody');
  if (!tbody) return;

  const state = getState();

  // Table Info Banner
  const infoSpan = document.getElementById('tableInfoCE');
  if (infoSpan) {
    if (state.isDocumentLoaded && state.uploadedFiles && state.uploadedFiles.length > 0) {
      infoSpan.innerHTML = `📄 <strong>Documento Elaborato:</strong> ${state.uploadedFiles.join(', ')} — 100% Parametri Civilistici Estratti`;
      infoSpan.style.color = 'var(--accent-green)';
    } else {
      infoSpan.innerHTML = `⚠️ <strong>Nessun Documento Caricato</strong>. Vai su "Ingestione Documenti ERP" per elaborare un bilancio.`;
      infoSpan.style.color = 'var(--accent-amber)';
    }
  }

  // Adaptive Data-Driven Timeline Header & Badges
  const thead = document.querySelector('#ceTableContainer thead tr');
  const timeline = getTimelineYears();
  const maxCol = timeline.length;

  // Render active years badges in toolbar
  const badgesContainer = document.getElementById('activeYearsBadgesContainer');
  if (badgesContainer) {
    let badgesHTML = '';
    timeline.forEach(t => {
      const bClass = t.isPivot ? 'pivot-badge-y0' : (t.relOffset < 0 ? 'pivot-badge-ypast' : 'pivot-badge-yfuture');
      const manualTag = t.isManual ? ' ✏️' : '';
      badgesHTML += `<span class="pivot-badge ${bClass}" style="font-size:0.72rem; padding: 2px 6px; border-radius: 4px; display:inline-flex; align-items:center; gap:2px;">${t.label} (${t.year})${manualTag}</span>`;
    });
    badgesContainer.innerHTML = badgesHTML;
  }

  if (thead) {
    let headHTML = `<th>Voce Civilistica (Art. 2425 C.C.)</th>`;
    for (let c = 0; c < maxCol; c++) {
      const t = timeline[c];
      const badgeClass = t.isPivot ? 'pivot-badge-y0' : (t.relOffset < 0 ? 'pivot-badge-ypast' : 'pivot-badge-yfuture');
      const colClass = t.isPivot ? 'editable-col th-pivot-y0' : (t.relOffset < 0 ? 'th-past-actual' : 'th-future-forecast');

      let gapBadge = '';
      if (c > 0 && Math.abs(t.year - timeline[c - 1].year) > 1) {
        gapBadge = `<span class="gap-badge" style="background:#f59e0b; color:#0f172a; font-size:0.68rem; font-weight:800; padding:1px 4px; border-radius:3px; margin-right:4px;">⚡ GAP</span>`;
      }
      let removeBtn = '';
      if (t.isManual) {
        removeBtn = `<button onclick="event.stopPropagation(); window.removeTimelineYear(${t.year})" title="Rimuovi colonna ${t.year}" style="background:transparent; border:none; color:#ef4444; font-size:0.75rem; cursor:pointer; margin-left:4px; padding:0 2px;">🗑️</button>`;
      }
      headHTML += `<th class="${colClass}">${gapBadge}<span class="pivot-badge ${badgeClass}">${t.label}</span> (${t.year})${removeBtn}</th>`;
    }
    thead.innerHTML = headHTML;
  }

  const y = state.years || [];
  const fmt = (num) => formatEuro(num);

  // Sub-righe CE
  let ricaviVenditeSubrowsHTML = '';
  let altriRicaviSubrowsHTML = '';
  let b6SubrowsHTML = '';
  let b7SubrowsHTML = '';
  let b8SubrowsHTML = '';
  let persSubrowsHTML = '';
  let b10aSubrowsHTML = '';
  let b10bSubrowsHTML = '';
  let b10cSubrowsHTML = '';
  let b14SubrowsHTML = '';

  let ricaviVenditeCount = 0;
  let altriRicaviCount = 0;
  let b6Count = 0;
  let b7Count = 0;
  let b8Count = 0;
  let persCount = 0;
  let b10aCount = 0;
  let b10bCount = 0;
  let b10cCount = 0;
  let b14Count = 0;

  if (state.detailedSubitems && state.detailedSubitems.length > 0) {
    const uniqueItemsMap = new Map();
    state.detailedSubitems.forEach(item => {
      const itemLabel = (item.label || item.name || item.id || '').trim();
      if (!itemLabel) return;
      const key = `${item.section}_${itemLabel}`;
      if (!uniqueItemsMap.has(key)) {
        uniqueItemsMap.set(key, {
          id: item.id || itemLabel,
          label: itemLabel,
          section: item.section,
          entriesByYear: {}
        });
      }
      const group = uniqueItemsMap.get(key);
      const yr = parseInt(item.year, 10) || state.pivotYear || 2025;
      const val = (item.value !== undefined) ? item.value : (item.amount || 0);
      group.entriesByYear[yr] = val;
      if (item.value_y0 !== undefined) {
        group.entriesByYear[state.pivotYear || 2025] = item.value_y0;
      }
      if (item.value_yprev !== undefined) {
        group.entriesByYear[(state.pivotYear || 2025) - 1] = item.value_yprev;
      }
    });

    uniqueItemsMap.forEach(group => {
      const subId = group.id;
      const hasAnyValue = Object.values(group.entriesByYear).some(v => Math.abs(v) > 0.01);
      if (!hasAnyValue) return;

      const deleteBtn = `<button class="btn-delete-subitem" data-subitem-id="${subId}" data-section="${group.section}" title="Elimina Voce">🗑️</button>`;

      let colsStr = '';
      for (let c = 0; c < maxCol; c++) {
        const colYear = timeline[c] ? timeline[c].year : (state.pivotYear || 2025);
        const overrideKey = `subitem_${group.section}_${subId}_${c}`;
        const isOverride = !!(state.manualOverrides && state.manualOverrides[overrideKey]);
        const overrideClass = isOverride ? ' manual-override' : '';

        const val = group.entriesByYear[colYear];
        if (val !== undefined && val !== null && !isNaN(val)) {
          colsStr += `<td class="editable-cell${overrideClass}" data-type="subitem" data-section="${group.section}" data-subitem-id="${subId}" data-index="${c}" data-year="${colYear}">${fmt(val)}</td>`;
        } else {
          colsStr += `<td>--</td>`;
        }
      }

      let subClass = 'subrow-generic';
      const sec = group.section;
      if (sec === 'ricaviVendite' || (sec === 'ricavi' && group.label.toLowerCase().includes('didattica'))) subClass = 'subrow-ricavi-vendite';
      else if (sec === 'altriRicavi' || sec === 'ricavi') subClass = 'subrow-altri-ricavi';
      else if (sec === 'costiMaterieHosting') subClass = 'subrow-b6';
      else if (sec === 'costiServiziMarketing' || sec === 'opex') subClass = 'subrow-b7';
      else if (sec === 'costiGodimentoBeni') subClass = 'subrow-b8';
      else if (sec === 'personale' || sec === 'salariStipendi' || sec === 'oneriSociali' || sec === 'tfrQuota') subClass = 'subrow-personale';
      else if (sec === 'ammImmateriali' || sec === 'ammImm') subClass = 'subrow-b10a';
      else if (sec === 'ammMateriali' || sec === 'ammMat' || sec === 'ammortamenti') subClass = 'subrow-b10b';
      else if (sec === 'svalutazioneCrediti' || sec === 'svalutazione') subClass = 'subrow-b10c';
      else if (sec === 'oneriDiversi' || sec === 'custom') subClass = 'subrow-b14';

      const rowHTML = `
        <tr class="${subClass}" style="background: rgba(30, 41, 59, 0.4); font-size: 0.82rem; color: #cbd5e1;">
          <td style="padding-left: 3rem; display: flex; align-items: center; justify-content: space-between;">
            <span class="editable-label" data-type="subitem-label" data-subitem-id="${subId}" data-section="${group.section}" contenteditable="${state.editMode ? 'true' : 'false'}">└── ${group.label}</span>
            ${deleteBtn}
          </td>
          ${colsStr}
        </tr>
      `;

      if (subClass === 'subrow-ricavi-vendite') { ricaviVenditeSubrowsHTML += rowHTML; ricaviVenditeCount++; }
      else if (subClass === 'subrow-altri-ricavi') { altriRicaviSubrowsHTML += rowHTML; altriRicaviCount++; }
      else if (subClass === 'subrow-b6') { b6SubrowsHTML += rowHTML; b6Count++; }
      else if (subClass === 'subrow-b7') { b7SubrowsHTML += rowHTML; b7Count++; }
      else if (subClass === 'subrow-b8') { b8SubrowsHTML += rowHTML; b8Count++; }
      else if (subClass === 'subrow-personale') { persSubrowsHTML += rowHTML; persCount++; }
      else if (subClass === 'subrow-b10a') { b10aSubrowsHTML += rowHTML; b10aCount++; }
      else if (subClass === 'subrow-b10b') { b10bSubrowsHTML += rowHTML; b10bCount++; }
      else if (subClass === 'subrow-b10c') { b10cSubrowsHTML += rowHTML; b10cCount++; }
      else if (subClass === 'subrow-b14') { b14SubrowsHTML += rowHTML; b14Count++; }
    });
  }

  const rCells = (fieldName, isEditable = true) => {
    let str = '';
    for (let c = 0; c < maxCol; c++) {
      const val = (y[c] && y[c][fieldName] !== undefined) ? y[c][fieldName] : 0;
      const overrideKey = `ce_${fieldName}_${c}`;
      const isOverride = !!(state.manualOverrides && state.manualOverrides[overrideKey]);
      const overrideClass = isOverride ? ' manual-override' : '';
      const lineage = getLineageInfo('ce', fieldName, c);

      if (isEditable) {
        str += `<td class="editable-cell${overrideClass} lineage-cell" data-section="ce" data-field="${fieldName}" data-index="${c}" data-source-file="${lineage.file}" data-source-path="${lineage.path}" data-source-type="${lineage.type}">${fmt(val)}</td>`;
      } else {
        str += `<td class="lineage-cell" data-source-file="${lineage.file}" data-source-path="${lineage.path}" data-source-type="${lineage.type}">${fmt(val)}</td>`;
      }
    }
    return str;
  };

  const totalCols = maxCol + 1;

  tbody.innerHTML = `
    <tr class="row-section-header"><td colspan="${totalCols}">A) VALORE DELLA PRODUZIONE</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        A.1) Ricavi delle Vendite e Prestazioni (Proventi Didattica / SaaS)
        ${ricaviVenditeCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-ricavi-vendite" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${ricaviVenditeCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('ricaviVendite', true)}
    </tr>
    ${ricaviVenditeSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">A.2) Variazioni delle Rimanenze di Prodotti in corso di lavorazione, semilavorati e finiti</td>
      ${rCells('variazRimanenze', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">A.3) Variazioni dei Lavori in corso su ordinazione</td>
      ${rCells('variazLavoriCorso', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">A.4) Incrementi di Immobilizzazioni per lavori interni</td>
      ${rCells('lavoriInterni', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        A.5) Altri Ricavi e Proventi (Contributi MIUR / R&S / Enti)
        ${altriRicaviCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-altri-ricavi" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${altriRicaviCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('altriRicavi', true)}
    </tr>
    ${altriRicaviSubrowsHTML}
    <tr class="row-subtotal" title="Equazione: A.1 + A.2 + A.3 + A.4 + A.5">
      <td>TOTALE VALORE DELLA PRODUZIONE (A) = A.1 + A.2 + A.3 + A.4 + A.5</td>
      ${rCells('ricaviTot', false)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">B) COSTI DELLA PRODUZIONE</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        B.6) Materie Prime, Sussidiarie, di Consumo e Merci
        ${b6Count > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-b6" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${b6Count} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('costiMaterieHosting', true)}
    </tr>
    ${b6SubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">
        B.7) Costi per Servizi Operativi & Didattica/Consulenze
        ${b7Count > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-b7" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${b7Count} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('costiServiziMarketing', true)}
    </tr>
    ${b7SubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">
        B.8) Godimento Beni di Terzi (Affitti / Licenze SaaS)
        ${b8Count > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-b8" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${b8Count} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('costiGodimentoBeni', true)}
    </tr>
    ${b8SubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">
        B.9.a) Salari e Stipendi Personale Dipendente / Docenti
        ${persCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-personale" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${persCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('salariStipendi', true)}
    </tr>
    ${persSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">B.9.b) Oneri Sociali (INPS / INAIL)</td>
      ${rCells('oneriSociali', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem; color: var(--accent-amber);">B.9.c) Trattamento di Fine Rapporto (Quota TFR)</td>
      ${rCells('tfrQuota', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        B.14) Oneri Diversi di Gestione
        ${b14Count > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-b14" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${b14Count} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('oneriDiversi', true)}
    </tr>
    ${b14SubrowsHTML}

    <tr class="row-total ${(y[0] && y[0].ebitda < 0) ? 'row-negative' : 'row-highlight'}" title="Equazione: A.Tot - (B.OpEx + B.Personale)">
      <td>[=] EBITDA = A.Tot - (B.OpEx + B.Personale)</td>
      ${rCells('ebitda', false)}
    </tr>

    <tr>
      <td style="padding-left: 1.5rem;">
        B.10.a) Ammortamento Immobilizzazioni Immateriali (Software IP)
        ${b10aCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-b10a" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${b10aCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('ammImm', true)}
    </tr>
    ${b10aSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">
        B.10.b) Ammortamento Immobilizzazioni Materiali (Server HW / Immobili)
        ${b10bCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-b10b" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${b10bCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('ammMat', true)}
    </tr>
    ${b10bSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">
        B.10.c) Svalutazione Crediti Commerciali / Attivo Circolante
        ${b10cCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-b10c" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${b10cCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCells('svalutazione', true)}
    </tr>
    ${b10cSubrowsHTML}

    <tr class="row-total" title="Equazione: EBITDA - AmmortamentiTot">
      <td>[=] EBIT (Risultato Operativo) = EBITDA - B.10.Ammortamenti</td>
      ${rCells('ebit', false)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">C) PROVENTI ED ONERI FINANZIARI</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">C.16) Altri Proventi Finanziari</td>
      ${rCells('proventiFin', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">C.17) Interessi ed Altri Oneri Finanziari</td>
      ${rCells('oneriFin', true)}
    </tr>

    <tr class="row-subtotal" title="Equazione D.Lgs. 139/2015: EBIT + C.ProventiFin - C.OneriFin">
      <td>[=] EBT (Risultato Prima delle Imposte) = EBIT + C.Proventi/Oneri Finanziari</td>
      ${rCells('ebt', false)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">20) IMPOSTE SUL REDDITO DELL'ESERCIZIO</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">20) Imposte sul Reddito dell'Esercizio (IRAP / IRES / Correnti)</td>
      ${rCells('imposteReddito', true)}
    </tr>

    <tr class="row-total ${(y[0] && y[0].utile < 0) ? 'row-negative' : 'row-highlight'}" title="Equazione: EBT - 20.Imposte">
      <td>🏆 21) UTILE (PERDITA) DELL'ESERCIZIO = EBT - 20.Imposte sul Reddito</td>
      ${rCells('utile', false)}
    </tr>
  `;

  initCETableEventDelegation();
}

// 🎯 EVENT DELEGATION PERMANENTE SU #ceTableContainer
export function initCETableEventDelegation() {
  if (typeof document === 'undefined') return;
  const container = document.getElementById('ceTableContainer');
  if (!container || container.dataset.eventsBound === 'true') return;

  container.dataset.eventsBound = 'true';

  // 1. Click delegation: Toggle Subrows & Delete Subitems
  container.addEventListener('click', (e) => {
    const toggleBtn = e.target.closest('.subrow-toggle-btn');
    if (toggleBtn) {
      e.stopPropagation();
      const targetClass = toggleBtn.dataset.target;
      if (targetClass) {
        document.querySelectorAll('.' + targetClass).forEach(el => {
          el.style.display = (el.style.display === 'none' ? '' : 'none');
        });
      }
      return;
    }

    const deleteBtn = e.target.closest('.btn-delete-subitem');
    if (deleteBtn) {
      e.stopPropagation();
      const subId = deleteBtn.dataset.subitemId;
      const section = deleteBtn.dataset.section;
      if (typeof window.deleteSubitem === 'function') {
        window.deleteSubitem(subId, section);
      }
      return;
    }
  });

  // 2. Double-Click delegation: Cell Editing
  container.addEventListener('dblclick', (e) => {
    const editableCell = e.target.closest('.editable-cell');
    if (!editableCell) return;

    const cellType = editableCell.dataset.type;
    if (cellType === 'subitem') {
      const subId = editableCell.dataset.subitemId;
      const section = editableCell.dataset.section;
      const year = parseInt(editableCell.dataset.year, 10);
      const state = getState();
      const item = (state.detailedSubitems || []).find(s => (s.id === subId || s.label === subId) && (!s.year || s.year === year));
      const currentVal = item ? (item.value || 0) : 0;
      const input = prompt(`Inserisci nuovo valore per sub-voce (${year}):`, currentVal);
      if (input !== null) {
        const val = parseFloat(input);
        if (!isNaN(val)) {
          if (item) item.value = val;
          recalculateFinancials();
          renderCETable();
          renderSPTables();
          renderKpiCards();
          renderCharts();
          triggerTableFlash();
          showToast(`✅ Sub-voce aggiornata a €${val.toLocaleString('it-IT')}!`, 'success');
        }
      }
    } else {
      const section = editableCell.dataset.section;
      const field = editableCell.dataset.field;
      const index = parseInt(editableCell.dataset.index, 10);
      if (section && field && !isNaN(index)) {
        editFullField(section, field, index);
      }
    }
  });
}

export function openDetailedSubitemsModal() {
  document.getElementById('detailedSubitemsModal')?.classList.add('open');
}

export function closeDetailedSubitemsModal() {
  document.getElementById('detailedSubitemsModal')?.classList.remove('open');
}

export function updateManualCategoryOptions() {
  const sectionSelect = document.getElementById('manualItemSection');
  const catSelect = document.getElementById('manualItemCategory');
  if (!sectionSelect || !catSelect) return;

  const sec = sectionSelect.value;
  if (sec === 'ce') {
    catSelect.innerHTML = `
      <option value="ricavi" selected>A.1/A.5 Ricavi & Proventi</option>
      <option value="opex">B.6/B.7/B.8 Costi Operativi, Materie & Servizi</option>
      <option value="personale">B.9 Salari, Stipendi, Oneri & TFR</option>
      <option value="ammortamenti">B.10 Ammortamenti & Svalutazioni</option>
      <option value="finanziari">C.16/C.17 Proventi & Oneri Finanziari</option>
      <option value="imposte">20) Imposte sul Reddito</option>
    `;
  } else {
    catSelect.innerHTML = `
      <option value="immateriali">B.I Immobilizzazioni Immateriali</option>
      <option value="materiali">B.II Immobilizzazioni Materiali</option>
      <option value="finanziarie">B.III Immobilizzazioni Finanziarie</option>
      <option value="rimanenze">C.I Rimanenze</option>
      <option value="crediti" selected>C.II Crediti Commerciali & Tributari</option>
      <option value="cassa">C.IV Disponibilità Liquide</option>
      <option value="patrimonio">A) Patrimonio Netto & Riserve</option>
      <option value="debiti">D) Debiti verso Fornitori / Banche</option>
      <option value="ratei">D/E) Ratei e Risconti Attivi/Passivi</option>
    `;
  }
}

export function insertManualSubitem(event) {
  if (event) event.preventDefault();
  const labelInput = document.getElementById('manualItemLabel');
  const sectionSelect = document.getElementById('manualItemSection');
  const categorySelect = document.getElementById('manualItemCategory');
  const yearSelect = document.getElementById('manualItemYear');
  const amountInput = document.getElementById('manualItemAmount');

  if (!labelInput || !amountInput) return;

  const label = labelInput.value.trim();
  const amount = parseFloat(amountInput.value);

  if (!label || isNaN(amount)) {
    showToast("⚠️ Inserisci un nome ed un importo numerico valido!", "warning");
    return;
  }

  const category = categorySelect.value;
  let yearStr = yearSelect.value || "2025";
  let targetYear = parseInt(yearStr.replace('FY', ''), 10) || 2025;

  const uniqueId = 'manual_subitem_' + (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Date.now());

  const state = getState();
  state.detailedSubitems = state.detailedSubitems || [];
  const newItem = {
    id: uniqueId,
    label: label,
    section: category,
    value: amount,
    year: targetYear,
    source: 'MANUAL_ENTRY'
  };

  state.detailedSubitems.push(newItem);
  state.isDocumentLoaded = true;

  ensureYearRecord(targetYear);
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  triggerTableFlash();

  showToast(`➕ Voce "${label}" (€${amount.toLocaleString('it-IT')}) inserita nel bilancio (${targetYear})!`, 'success');
  labelInput.value = '';
  amountInput.value = '';
}

export function editFullField(section, key, index) {
  const state = getState();
  if (state.godMode) return;
  const timeline = getTimelineYears();
  const target = timeline[index];
  const year = target ? target.year : (2025 + index);
  const record = ensureYearRecord(year, target ? target.tag : 'actual');

  let currentVal = 0;
  if (record[section] && record[section][key] !== undefined) {
    currentVal = record[section][key];
  } else if (state.fullData && state.fullData[section] && state.fullData[section][key]) {
    currentVal = Array.isArray(state.fullData[section][key]) ? (state.fullData[section][key][index] || 0) : state.fullData[section][key];
  }

  const input = prompt(`Inserisci nuovo valore per ${key} (${target ? target.label : 'Anno ' + (index + 1)} - ${year}):`, currentVal);
  if (input !== null) {
    const val = parseFloat(input);
    if (!isNaN(val) && val >= 0) {
      if (record[section]) {
        record[section][key] = val;
      }
      if (state.fullData && state.fullData[section] && state.fullData[section][key]) {
        if (Array.isArray(state.fullData[section][key])) {
          state.fullData[section][key][index] = val;
        } else if (index === 0) {
          state.fullData[section][key] = val;
        }
      }
      const overrideKey = `${section}_${key}_${index}`;
      state.manualOverrides = state.manualOverrides || {};
      state.manualOverrides[overrideKey] = true;

      recalculateFinancials();
      renderCETable();
      renderSPTables();
      renderKpiCards();
      renderCharts();
      triggerTableFlash();
      showToast(`✅ Valore per ${key} aggiornato a €${val.toLocaleString('it-IT')}!`, 'success');
    } else {
      showToast("⚠️ Inserisci un numero valido ed esente da caratteri speciali!", "warning");
    }
  }
}

if (typeof window !== 'undefined') {
  window.toggleSubrows = function(cls) {
    document.querySelectorAll('.' + cls).forEach(el => {
      el.style.display = (el.style.display === 'none' ? '' : 'none');
    });
  };
}
