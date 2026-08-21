// 🏛️ MODALS & INTERACTION CONTROLLER - NODO 3 (ES6 Module)
// Modals, Toast Engine, Drawer Guida, Limbo & Reconciliation HITL

import { getState, setState, ensureYearRecord, setPivotYear } from './state.js';
import { recalculateFinancials } from './financial_engine.js';
import { renderCETable } from './table_ce.js';
import { renderSPTables } from './table_sp.js';
import { renderKpiCards, renderCharts } from './kpi_analytics.js';
import { formatEuro } from './constants.js';

export function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer') || createToastContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('fade-out');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function createToastContainer() {
  const div = document.createElement('div');
  div.id = 'toastContainer';
  div.className = 'toast-container';
  document.body.appendChild(div);
  return div;
}

export function triggerTableFlash() {
  const tables = document.querySelectorAll('.table-container table');
  tables.forEach(t => {
    t.classList.remove('table-flash');
    void t.offsetWidth;
    t.classList.add('table-flash');
  });
}

// 📦 MODAL APERTURA / CHIUSURA HELPERS
export function openExportModal() { document.getElementById('exportModal')?.classList.add('open'); }
export function closeExportModal() { document.getElementById('exportModal')?.classList.remove('open'); }

export function openConflictModal() { document.getElementById('conflictModal')?.classList.add('open'); }
export function closeConflictModal() { document.getElementById('conflictModal')?.classList.remove('open'); }

export function openGatewayModal() { document.getElementById('gatewayModal')?.classList.add('open'); }
export function closeGatewayModal() { document.getElementById('gatewayModal')?.classList.remove('open'); }

export function openFormulaModal() { document.getElementById('formulaModal')?.classList.add('open'); }
export function closeFormulaModal() { document.getElementById('formulaModal')?.classList.remove('open'); }

export function switchTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
    const onclickStr = btn.getAttribute('onclick') || '';
    if (onclickStr.includes(`'${tabId}'`)) {
      btn.classList.add('active');
    }
  });
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

  const targetTab = document.getElementById(`tab-${tabId}`);
  if (targetTab) {
    targetTab.classList.add('active');
  }
}

export function togglePrivacyShield() {
  const state = getState();
  const newShield = !state.privacyShield;
  setState({ privacyShield: newShield });

  const badge = document.getElementById('shieldStatus');
  if (badge) {
    badge.className = newShield ? 'status-badge shield-badge' : 'status-badge';
    badge.innerHTML = newShield 
      ? `<span class="badge-dot green"></span> Privacy Shield: GDPR Active` 
      : `<span class="badge-dot"></span> Privacy Shield: OFF`;
  }
  showToast(newShield ? "🛡️ Privacy Shield Attivo (GDPR Masking On)" : "⚠️ Privacy Shield Disattivato", newShield ? "success" : "warning");
}

export function toggleGodMode() {
  const toggle = document.getElementById('godModeToggle');
  const isGod = toggle ? toggle.checked : false;
  setState({ godMode: isGod });
  showToast(isGod 
    ? "⚡ God Mode Attivata: Override Allarmi Disabilitato!" 
    : "🛡️ God Mode Disattivata: Controlli Standard Attivi", isGod ? "warning" : "success");
}

// 🗂️ GESTIONE SUBITEMS MODAL
export function deleteSubitem(subId, section) {
  const state = getState();
  if (!state.detailedSubitems) return;
  const idx = state.detailedSubitems.findIndex(i => (i.id === subId || i.label === subId) && i.section === section);
  if (idx !== -1) {
    const item = state.detailedSubitems[idx];
    state.detailedSubitems.splice(idx, 1);
    recalculateFinancials();
    renderCETable();
    renderSPTables();
    renderKpiCards();
    renderCharts();
    showToast(`🗑️ Sottovoce '${item.label}' eliminata`, 'info');
  }
}

// 📑 GESTIONE CONFRONTO BI-ANNUALE
export function showComparativeYearModal(prevData) {
  const state = getState();
  state.pendingPreviousYearData = prevData;
  const modal = document.getElementById('comparativeYearModal');
  if (!modal) return;

  const curElem = document.getElementById('compYearCurrentPreview');
  const prevElem = document.getElementById('compYearPrevPreview');
  if (curElem) curElem.textContent = 'Caricato (Anno 2025)';
  if (prevElem) prevElem.textContent = 'Caricato (Anno 2024)';

  modal.style.display = 'flex';
}

export function closeComparativeYearModal() {
  const modal = document.getElementById('comparativeYearModal');
  if (modal) modal.style.display = 'none';
}

export function enableComparativeMode() {
  closeComparativeYearModal();
  const state = getState();
  if (state.pendingPreviousYearData) {
    const prevYear = 2024;
    const rec2024 = ensureYearRecord(prevYear, 'actual');
    const pData = state.pendingPreviousYearData;

    if (pData.ce) {
      for (const k in pData.ce) {
        if (rec2024.ce[k] !== undefined) rec2024.ce[k] = pData.ce[k];
      }
    }
    if (pData.sp) {
      if (pData.sp.capitaleSociale !== undefined && pData.sp.capitaleSociale > 0) {
        rec2024.sp.capitaleSociale = pData.sp.capitaleSociale;
      }
      for (const k in pData.sp) {
        if (k !== 'capitaleSociale' && rec2024.sp[k] !== undefined) {
          rec2024.sp[k] = pData.sp[k];
        }
      }
    }
    if (pData.detailedSubitems) {
      state.detailedSubitems = (state.detailedSubitems || []).concat(pData.detailedSubitems);
    }
  }

  state.isComparativeEnabled = true;
  state.visibleYearsCount = 2;
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  showToast('📊 Confronto Bi-Annuale (2025 vs 2024) Attivato!', 'success');
}

export function dismissComparativeMode() {
  closeComparativeYearModal();
  const state = getState();
  state.isComparativeEnabled = false;
  state.visibleYearsCount = 1;
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  showToast('Single-Year 2025 Mantenuto (Confronto Disattivato)', 'info');
}

// 🎯 GESTIONE PIVOT YEAR SELECTION MODAL
let tempSelectedPivotYear = null;

export function showPivotYearSelectionModal(availableYears = [2025, 2024], defaultYear = 2025) {
  tempSelectedPivotYear = defaultYear;
  const container = document.getElementById('pivotOptionsContainer');
  const modal = document.getElementById('pivotYearSelectionModal');
  if (!modal || !container) return;

  let html = '';
  availableYears.forEach(yr => {
    const isSelected = (yr === defaultYear);
    html += `
      <div class="pivot-option-card ${isSelected ? 'selected-pivot' : ''}" id="pivotOpt_${yr}" onclick="window.selectPivotOption(${yr})" style="cursor: pointer; padding: 1rem 1.5rem; border-radius: 8px; border: 2px solid ${isSelected ? 'var(--color-y0-pivot)' : 'var(--border-color)'}; background: ${isSelected ? 'rgba(245, 158, 11, 0.15)' : 'rgba(15, 23, 42, 0.6)'}; text-align: center; transition: all 0.2s ease;">
        <span style="font-size: 1.5rem; display: block; margin-bottom: 0.25rem; color: ${isSelected ? 'var(--color-y0-pivot)' : 'var(--text-muted)'};">★</span>
        <strong style="font-size: 1.1rem; color: var(--text-bright);">Esercizio ${yr}</strong>
        <p style="font-size: 0.75rem; color: var(--text-muted); margin: 0.25rem 0 0 0;">Imposta ${yr} come Anno Perno (Y0)</p>
      </div>
    `;
  });
  container.innerHTML = html;
  modal.style.display = 'flex';
}

export function selectPivotOption(yr) {
  tempSelectedPivotYear = yr;
  const container = document.getElementById('pivotOptionsContainer');
  if (!container) return;
  container.querySelectorAll('.pivot-option-card').forEach(card => {
    card.style.borderColor = 'var(--border-color)';
    card.style.background = 'rgba(15, 23, 42, 0.6)';
    card.classList.remove('selected-pivot');
    const star = card.querySelector('span');
    if (star) star.style.color = 'var(--text-muted)';
  });
  const target = document.getElementById(`pivotOpt_${yr}`);
  if (target) {
    target.style.borderColor = 'var(--color-y0-pivot)';
    target.style.background = 'rgba(245, 158, 11, 0.15)';
    target.classList.add('selected-pivot');
    const star = target.querySelector('span');
    if (star) star.style.color = 'var(--color-y0-pivot)';
  }
}

export function closePivotYearSelectionModal() {
  const modal = document.getElementById('pivotYearSelectionModal');
  if (modal) modal.style.display = 'none';
}

export function confirmPivotYearSelection() {
  const state = getState();
  const selected = tempSelectedPivotYear || state.pivotYear || 2025;
  closePivotYearSelectionModal();
  setPivotYear(selected);
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  showToast(`★ Esercizio ${selected} impostato con successo come Anno Perno Y0!`, 'success');
}

// 🛡️ RESET & OVERWRITE CONFIRMATION MODALS
export function openResetConfirmModal() {
  document.getElementById('resetConfirmModal')?.classList.add('open');
}

export function closeResetConfirmModal() {
  document.getElementById('resetConfirmModal')?.classList.remove('open');
}

export function confirmGlobalReset() {
  closeResetConfirmModal();
  if (typeof window !== 'undefined' && typeof window.globalResetSession === 'function') {
    window.globalResetSession(true);
  }
}

let overwriteResolver = null;

export function closeOverwriteConfirmModal(confirmed = false) {
  const modal = document.getElementById('overwriteConfirmModal');
  if (modal) modal.style.display = 'none';
  if (overwriteResolver) {
    overwriteResolver(confirmed);
    overwriteResolver = null;
  }
}

export function promptOverwriteConfirmation(year) {
  return new Promise((resolve) => {
    overwriteResolver = resolve;
    const modal = document.getElementById('overwriteConfirmModal');
    const span = document.getElementById('overwriteYearSpan');
    const confirmBtn = document.getElementById('confirmOverwriteBtn');

    if (span) span.textContent = year;
    if (confirmBtn) {
      confirmBtn.onclick = () => closeOverwriteConfirmModal(true);
    }
    if (modal) modal.style.display = 'flex';
  });
}

export function resolveConflict(value) {
  closeConflictModal();
  const state = getState();
  const pivotYear = state.pivotYear || 2025;
  const record = ensureYearRecord(pivotYear, 'actual');
  const numVal = parseFloat(value) || 0;
  if (record && record.ce) {
    record.ce.ricaviVendite = numVal;
  }
  if (state.fullData && state.fullData.ce && state.fullData.ce.ricaviVendite) {
    if (Array.isArray(state.fullData.ce.ricaviVendite)) {
      state.fullData.ce.ricaviVendite[0] = numVal;
    }
  }
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  triggerTableFlash();
  showToast(`✅ Conflitto risolto: Ricavi Vendite impostati a €${numVal.toLocaleString('it-IT')}`, 'success');
}

// 💡 GUIDA OPERATIVA INLINE ACCORDION DRAWER
export function toggleGuidaDrawer() {
  const drawer = document.getElementById('guidaAccordionDrawer');
  if (!drawer) return;

  const isOpen = drawer.classList.toggle('open');
  const btn = document.getElementById('btnToggleGuida');

  if (isOpen) {
    if (btn) btn.innerHTML = `<span class="btn-icon">💡</span> Guida Aperta (Clicca per Riduci)`;
    showToast("💡 Guida Operativa Espansa Inline — Leggi e Clicca sui Tasti!", "info");
  } else {
    if (btn) btn.innerHTML = `<span class="btn-icon">💡</span> Guida Operativa (Espandi / Riduci)`;
    showToast("💡 Guida Operativa Ridotta", "info");
  }
}

export function openGuidaModal() { toggleGuidaDrawer(); }
export function closeGuidaModal() {
  const drawer = document.getElementById('guidaAccordionDrawer');
  if (drawer) drawer.classList.remove('open');
}

export function switchGuidaTab(tabId, e) {
  document.querySelectorAll('.guida-tab-btn').forEach(btn => {
    btn.classList.remove('active');
    const onclickStr = btn.getAttribute('onclick') || '';
    if (onclickStr.includes(`'${tabId}'`)) {
      btn.classList.add('active');
    }
  });
  document.querySelectorAll('.guida-tab-content').forEach(c => c.classList.remove('active'));

  if (e && e.target) {
    e.target.classList.add('active');
  }

  const targetTab = document.getElementById(`guida-tab-${tabId}`);
  if (targetTab) {
    targetTab.classList.add('active');
  }
}

// ✏️ QUICKFIX & EDIT CAPITALE SOCIALE
export function quickFixCapitaleSociale() {
  const state = getState();
  const pivotYear = state.pivotYear || 2025;
  const record = ensureYearRecord(pivotYear, 'actual');
  record.sp.capitaleSociale = 10000;
  if (state.fullData && state.fullData.sp) {
    state.fullData.sp.capitaleSociale = 10000;
  }
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  triggerTableFlash();
  showToast("✏️ Capitale Sociale aggiornato a €10.000 (S.r.l. conforme al Codice Civile)!", "success");
}

export function editCapitaleSociale() {
  const state = getState();
  const pivotYear = state.pivotYear || 2025;
  const record = ensureYearRecord(pivotYear, 'actual');
  const currentVal = record.sp.capitaleSociale || (state.fullData && state.fullData.sp && state.fullData.sp.capitaleSociale) || 0;
  const input = prompt("Inserisci valore Capitale Sociale iniziale (€):", currentVal);
  if (input !== null) {
    const val = parseFloat(input);
    if (!isNaN(val) && val >= 0) {
      record.sp.capitaleSociale = val;
      if (state.fullData && state.fullData.sp) {
        state.fullData.sp.capitaleSociale = val;
      }
      recalculateFinancials();
      renderCETable();
      renderSPTables();
      renderKpiCards();
      renderCharts();
      triggerTableFlash();
      showToast(`✏️ Capitale Sociale impostato a €${val.toLocaleString('it-IT')}!`, 'success');
    } else {
      showToast("⚠️ Inserisci una cifra valida per il Capitale Sociale!", "warning");
    }
  }
}

export { updateManualCategoryOptions } from './table_ce.js';
