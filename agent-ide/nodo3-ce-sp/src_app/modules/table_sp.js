// 🏛️ TABLE SP CONTROLLER & RENDERER - NODO 3 (ES6 Module)
// Stato Patrimoniale Art. 2424 C.C. | Attivo, Passivo & Patrimonio Netto
// Event Delegation Permanente & Sparse Bounded Horizon

import { getState, getTimelineYears } from './state.js';
import { formatEuro, MAX_VISIBLE_YEARS } from './constants.js';
import { getLineageInfo, editFullField } from './table_ce.js';
import { recalculateFinancials } from './financial_engine.js';
import { renderCETable } from './table_ce.js';
import { renderKpiCards, renderCharts } from './kpi_analytics.js';
import { showToast, triggerTableFlash } from './modals.js';

export function renderSPTables() {
  const attivoBody = document.getElementById('spAttivoBody');
  const passivoBody = document.getElementById('spPassivoBody');
  if (!attivoBody || !passivoBody) return;

  const state = getState();
  const y = state.years || [];
  const fmt = (num) => formatEuro(num);
  const timeline = getTimelineYears();
  const maxCol = timeline.length;
  const totalCols = maxCol + 1;

  // Thead Attivo e Passivo con Adaptive Data-Driven Timeline & GAP Badges
  const theadAttivo = document.querySelector('#tab-sp table:nth-of-type(1) thead tr');
  const theadPassivo = document.querySelector('#tab-sp table:nth-of-type(2) thead tr');

  if (theadAttivo) {
    let h = `<th>Voce Attivo</th>`;
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
      h += `<th class="${colClass}">${gapBadge}<span class="pivot-badge ${badgeClass}">${t.label}</span> (${t.year})${removeBtn}</th>`;
    }
    theadAttivo.innerHTML = h;
  }

  if (theadPassivo) {
    let h = `<th>Voce Passivo e Patrimonio Netto</th>`;
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
      h += `<th class="${colClass}">${gapBadge}<span class="pivot-badge ${badgeClass}">${t.label}</span> (${t.year})${removeBtn}</th>`;
    }
    theadPassivo.innerHTML = h;
  }

  const rCellsSP = (fieldName, isEditable = true) => {
    let str = '';
    for (let c = 0; c < maxCol; c++) {
      const val = (y[c] && y[c][fieldName] !== undefined) ? y[c][fieldName] : 0;
      const overrideKey = `sp_${fieldName}_${c}`;
      const isOverride = !!(state.manualOverrides && state.manualOverrides[overrideKey]);
      const overrideClass = isOverride ? ' manual-override' : '';
      const lineage = getLineageInfo('sp', fieldName, c);

      if (isEditable) {
        str += `<td class="editable-cell${overrideClass} lineage-cell" data-section="sp" data-field="${fieldName}" data-index="${c}" data-source-file="${lineage.file}" data-source-path="${lineage.path}" data-source-type="${lineage.type}">${fmt(val)}</td>`;
      } else {
        str += `<td class="lineage-cell" data-source-file="${lineage.file}" data-source-path="${lineage.path}" data-source-type="${lineage.type}">${fmt(val)}</td>`;
      }
    }
    return str;
  };

  // Sub-righe SP
  let immatSubrowsHTML = '';
  let matSubrowsHTML = '';
  let creditiSubrowsHTML = '';
  let cassaSubrowsHTML = '';
  let patrimonioSubrowsHTML = '';
  let debitiSubrowsHTML = '';

  let immatCount = 0;
  let matCount = 0;
  let creditiCount = 0;
  let cassaCount = 0;
  let patrimonioCount = 0;
  let debitiCount = 0;

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
      if (sec === 'immateriali' || sec === 'immaterialiLorde') subClass = 'subrow-immat';
      else if (sec === 'materiali' || sec === 'materialiLorde') subClass = 'subrow-mat';
      else if (sec === 'crediti' || sec === 'creditiClienti' || sec === 'creditiTributari') subClass = 'subrow-crediti';
      else if (sec === 'cassa') subClass = 'subrow-cassa';
      else if (sec === 'patrimonio' || sec === 'capitaleSociale' || sec === 'riserveUtili') subClass = 'subrow-patrimonio';
      else if (sec === 'debiti' || sec === 'debFornitori' || sec === 'debBanche' || sec === 'debTrib' || sec === 'debPrev') subClass = 'subrow-debiti';

      const rowHTML = `
        <tr class="${subClass}" style="background: rgba(30, 41, 59, 0.4); font-size: 0.82rem; color: #cbd5e1;">
          <td style="padding-left: 3rem; display: flex; align-items: center; justify-content: space-between;">
            <span class="editable-label" data-type="subitem-label" data-subitem-id="${subId}" data-section="${group.section}" contenteditable="${state.editMode ? 'true' : 'false'}">└── ${group.label}</span>
            ${deleteBtn}
          </td>
          ${colsStr}
        </tr>
      `;

      if (subClass === 'subrow-immat') { immatSubrowsHTML += rowHTML; immatCount++; }
      else if (subClass === 'subrow-mat') { matSubrowsHTML += rowHTML; matCount++; }
      else if (subClass === 'subrow-crediti') { creditiSubrowsHTML += rowHTML; creditiCount++; }
      else if (subClass === 'subrow-cassa') { cassaSubrowsHTML += rowHTML; cassaCount++; }
      else if (subClass === 'subrow-patrimonio') { patrimonioSubrowsHTML += rowHTML; patrimonioCount++; }
      else if (subClass === 'subrow-debiti') { debitiSubrowsHTML += rowHTML; debitiCount++; }
    });
  }

  // 1. Render ATTIVO
  attivoBody.innerHTML = `
    <tr class="row-section-header"><td colspan="${totalCols}">B) IMMOBILIZZAZIONI (ATTIVO FISSO)</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        B.I) Immobilizzazioni Immateriali Nette (Software / Brevetti)
        ${immatCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-immat" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${immatCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCellsSP('immNetteImm', true)}
    </tr>
    ${immatSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">
        B.II) Immobilizzazioni Materiali Nette (Immobili / Server)
        ${matCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-mat" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${matCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCellsSP('immNetteMat', true)}
    </tr>
    ${matSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">B.III) Immobilizzazioni Finanziarie (Depositi / Partecipazioni)</td>
      ${rCellsSP('immFin', true)}
    </tr>
    <tr class="row-subtotal" title="Equazione: B.I + B.II + B.III">
      <td>TOTALE IMMOBILIZZAZIONI (B) = B.I + B.II + B.III</td>
      ${rCellsSP('totaleImmobilizzazioni', false)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">C) ATTIVO CIRCOLANTE</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">C.I) Rimanenze di Magazzino (Merci e Prodotti)</td>
      ${rCellsSP('rimanenze', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        C.II.1) Crediti verso Clienti (Commerciali / Istituzionali)
        ${creditiCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-crediti" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${creditiCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCellsSP('creditiClienti', true)}
    </tr>
    ${creditiSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">C.II.5) Crediti Tributari & Imposte Anticipate</td>
      ${rCellsSP('creditiTributari', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        C.IV) Disponibilità Liquide (Cassa e Conti Correnti Bancari)
        ${cassaCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-cassa" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${cassaCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCellsSP('cassa', true)}
    </tr>
    ${cassaSubrowsHTML}
    <tr class="row-subtotal" title="Equazione: C.I + C.II + C.IV">
      <td>TOTALE ATTIVO CIRCOLANTE (C) = C.I + C.II + C.IV</td>
      ${rCellsSP('totaleAttivoCircolante', false)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">D) RATEI E RISCONTI ATTIVI</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">D) Ratei e Risconti Attivi</td>
      ${rCellsSP('rateiAttivi', true)}
    </tr>

    <tr class="row-total row-highlight" title="Equazione: B.Immob + C.AttivoCircolante + D.Ratei">
      <td>🏆 TOTALE ATTIVO = B + C + D</td>
      ${rCellsSP('totaleAttivo', false)}
    </tr>
  `;

  // 2. Render PASSIVO
  passivoBody.innerHTML = `
    <tr class="row-section-header"><td colspan="${totalCols}">A) PATRIMONIO NETTO</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">A.I) Capitale Sociale / Fondo di Dotazione</td>
      ${rCellsSP('capitaleSociale', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">A.IV) Riserva Legale</td>
      ${rCellsSP('riservaLegale', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        A.VIII) Riserve di Utili e Altre Riserve
        ${patrimonioCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-patrimonio" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${patrimonioCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCellsSP('riserveUtili', true)}
    </tr>
    ${patrimonioSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem; color: var(--accent-green); font-weight:600;">A.IX) Utile (Perdita) dell'Esercizio (da CE)</td>
      ${rCellsSP('utile', false)}
    </tr>
    <tr class="row-subtotal" title="Equazione: A.I + A.IV + A.VIII + A.IX">
      <td>TOTALE PATRIMONIO NETTO (A) = A.I + A.IV + A.VIII + A.IX</td>
      ${rCellsSP('patrimonioNetto', false)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">B) FONDI PER RISCHI ED ONERI & C) TFR</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">B) Fondi per Rischi ed Oneri</td>
      ${rCellsSP('fondiRischi', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">C) Trattamento di Fine Rapporto di Lavoro Subordinato (Fondo TFR)</td>
      ${rCellsSP('tfrFondo', true)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">D) DEBITI</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">D.4) Debiti verso Banche ed Istituti Finanziari</td>
      ${rCellsSP('debBanche', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">
        D.7) Debiti verso Fornitori
        ${debitiCount > 0 ? `<button class="subrow-toggle-btn badge-subcount" data-target="subrow-debiti" style="cursor:pointer; font-size:0.75rem; color:var(--accent-blue); margin-left:0.5rem; background:none; border:none; padding:0;">(${debitiCount} sub-voci ▾)</button>` : ''}
      </td>
      ${rCellsSP('debFornitori', true)}
    </tr>
    ${debitiSubrowsHTML}
    <tr>
      <td style="padding-left: 1.5rem;">D.12) Debiti Tributari (IRES / IRAP / IVA)</td>
      ${rCellsSP('debTrib', true)}
    </tr>
    <tr>
      <td style="padding-left: 1.5rem;">D.13) Debiti verso Istituti di Previdenza (INPS/INAIL)</td>
      ${rCellsSP('debPrev', true)}
    </tr>
    <tr class="row-subtotal" title="Equazione: D.4 + D.7 + D.12 + D.13">
      <td>TOTALE DEBITI (D) = D.4 + D.7 + D.12 + D.13</td>
      ${rCellsSP('totaleDebiti', false)}
    </tr>

    <tr class="row-section-header"><td colspan="${totalCols}">E) RATEI E RISCONTI PASSIVI</td></tr>
    <tr>
      <td style="padding-left: 1.5rem;">E) Ratei e Risconti Passivi / Contributi agli Investimenti</td>
      ${rCellsSP('rateiPassivi', true)}
    </tr>

    <tr class="row-total row-highlight" title="Equazione: A.Netto + B.Fondi + C.TFR + D.Debiti + E.Ratei">
      <td>🏆 TOTALE PASSIVO E PATRIMONIO NETTO = A + B + C + D + E</td>
      ${rCellsSP('totalePassivo', false)}
    </tr>
  `;

  initSPTableEventDelegation();
}

// 🎯 EVENT DELEGATION PERMANENTE SU #tab-sp / #spTableContainer
export function initSPTableEventDelegation() {
  if (typeof document === 'undefined') return;
  const container = document.getElementById('tab-sp') || document.getElementById('spTableContainer');
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
