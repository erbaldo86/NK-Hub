// 🏛️ CENTRAL REACTIVE STATE STORE - NODO 3 (ES6 Module)
// Single Source of Truth, Deep Reset Atomico & Period-Object Architecture
// Delta Ledger Replay Engine (INV-03 Zero Ghost Residues)

import { CE_KEYS, SP_KEYS } from './constants.js';

function createInitialState() {
  return {
    privacyShield: true,
    editMode: false,
    fsmState: 'VIEWING',
    gatewayMode: 'test',
    godMode: false,
    selectedAteco: 'saas',
    isDocumentLoaded: false,
    visibleYearsCount: 5,
    selectedTopKpiYearIndex: 2,
    selectedSidebarYearIndex: 2,
    activeFileCount: 0,
    deltaLedger: {},
    uploadedFiles: [],
    uploadedFilesDetails: [],
    detailedSubitems: [],
    exceptionsQueue: [],
    limboBucket: [],
    hitlMappings: {},
    manualOverrides: {},
    isComparativeEnabled: false,
    loadedDocumentType: 'FULL_BILANCIO',
    pendingPreviousYearData: null,
    detectedComparativeYears: [2025],
    pivotYear: 2025,
    scopePastYears: 2,
    scopeFutureYears: 2,
    manualExpandedYears: [],

    fullData: {
      baseYear: 2025,
      records: {},
      sortedYears: [2025, 2026, 2027, 2028, 2029],
      fy: ['FY2025', 'FY2026', 'FY2027', 'FY2028', 'FY2029'],
      ce: Object.fromEntries(CE_KEYS.map(k => [k, [0, 0, 0, 0, 0]])),
      sp: Object.fromEntries(SP_KEYS.map(k => [k, k === 'capitaleSociale' ? 0 : [0, 0, 0, 0, 0]]))
    },

    years: []
  };
}

let state = createInitialState();
const listeners = new Set();
let isBatching = false;

export function getState() {
  return state;
}

export function setState(updater) {
  if (typeof updater === 'function') {
    state = updater(state);
  } else if (typeof updater === 'object' && updater !== null) {
    state = { ...state, ...updater };
  }
  notify();
  return state;
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify() {
  if (isBatching) return;
  for (const listener of listeners) {
    try {
      listener(state);
    } catch (err) {
      console.error('[StateStore] Errore listener:', err);
    }
  }
}

// 📸 SNAPSHOT & ROLLBACK CONTROLLERS
export function takeStateSnapshot() {
  return JSON.parse(JSON.stringify(state));
}

export function restoreStateSnapshot(snapshot) {
  if (!snapshot) return state;
  state = JSON.parse(JSON.stringify(snapshot));
  notify();
  return state;
}

// 🧊 BATCH UPDATE WITH FROZEN NOTIFICATIONS
export function batchUpdate(updaterFn) {
  const previousBatching = isBatching;
  isBatching = true;
  try {
    if (typeof updaterFn === 'function') {
      updaterFn(state);
    }
  } finally {
    isBatching = previousBatching;
    if (!isBatching) {
      notify();
    }
  }
}

// 🧹 RESET ATOMICO RIGENERATIVO (Risolve INV-03: Zero Ghost Residues)
export function resetState() {
  const currentLedger = {};
  state = createInitialState();
  notify();
  return state;
}

// 📜 DELTA LEDGER REPLAY ENGINE (INV-03: Deterministic Zero Ghost Residues)
export function replayDeltaLedger() {
  batchUpdate(() => {
    const savedPivot = state.pivotYear || 2025;
    const ledger = state.deltaLedger || {};
    const fileIds = Object.keys(ledger);

    // 1. Reset calculation data to virgin zero base
    state.fullData = {
      baseYear: savedPivot,
      records: {},
      sortedYears: [savedPivot, savedPivot + 1, savedPivot + 2, savedPivot + 3, savedPivot + 4],
      fy: [0, 1, 2, 3, 4].map(i => `FY${savedPivot + i}`),
      ce: Object.fromEntries(CE_KEYS.map(k => [k, [0, 0, 0, 0, 0]])),
      sp: Object.fromEntries(SP_KEYS.map(k => [k, k === 'capitaleSociale' ? 0 : [0, 0, 0, 0, 0]]))
    };
    state.detailedSubitems = [];
    state.exceptionsQueue = [];
    state.uploadedFiles = [];
    state.uploadedFilesDetails = [];

    // 2. Sequential Replay of all registered file deltas
    for (const fileId of fileIds) {
      const entry = ledger[fileId];
      if (!entry) continue;

      const fileRecord = entry.fileRecord || {};
      const deltaData = entry.deltaData || {};

      // Register file details in UI registry
      if (fileRecord.filename) {
        state.uploadedFiles.push(fileRecord.filename);
        state.uploadedFilesDetails.push({
          id: fileId,
          name: fileRecord.filename,
          type: fileRecord.file_type || "ERP_DOC",
          sizeBytes: fileRecord.size_bytes || 0,
          paramsCount: fileRecord.extracted_items_count || 0,
          confidence: fileRecord.confidence_score || 0.95,
          timestamp: fileRecord.upload_timestamp || new Date().toISOString()
        });
      }

      const curTargetYear = deltaData.pivot_year || fileRecord.detected_years?.[0] || savedPivot;
      const prevYear = curTargetYear - 1;
      const recY0 = ensureYearRecord(curTargetYear, 'actual');
      const recYprev = ensureYearRecord(prevYear, 'actual');

      // Replay CE numbers
      const ceData = deltaData.ce || {};
      for (const k of CE_KEYS) {
        if (ceData[k] !== undefined) {
          const val0 = Array.isArray(ceData[k]) ? ceData[k][0] : ceData[k];
          if (val0 !== undefined && val0 !== null && !isNaN(val0)) {
            recY0.ce[k] = (recY0.ce[k] || 0) + Number(val0);
          }
          if (Array.isArray(ceData[k]) && ceData[k].length > 1) {
            const val1 = ceData[k][1];
            if (val1 !== undefined && val1 !== null && !isNaN(val1)) {
              recYprev.ce[k] = (recYprev.ce[k] || 0) + Number(val1);
            }
          }
        }
      }

      // Replay SP numbers
      const spData = deltaData.sp || {};
      if (spData.capitaleSociale !== undefined && spData.capitaleSociale !== null && !isNaN(spData.capitaleSociale)) {
        recY0.sp.capitaleSociale = Math.max(recY0.sp.capitaleSociale || 0, Number(spData.capitaleSociale));
        recYprev.sp.capitaleSociale = Math.max(recYprev.sp.capitaleSociale || 0, Number(spData.capitaleSociale));
      }
      for (const k of SP_KEYS) {
        if (k !== 'capitaleSociale' && spData[k] !== undefined) {
          const val0 = Array.isArray(spData[k]) ? spData[k][0] : spData[k];
          if (val0 !== undefined && val0 !== null && !isNaN(val0)) {
            recY0.sp[k] = (recY0.sp[k] || 0) + Number(val0);
          }
          if (Array.isArray(spData[k]) && spData[k].length > 1) {
            const val1 = spData[k][1];
            if (val1 !== undefined && val1 !== null && !isNaN(val1)) {
              recYprev.sp[k] = (recYprev.sp[k] || 0) + Number(val1);
            }
          }
        }
      }

      // Replay detailed subitems tagged with fileId
      if (deltaData.detailedSubitems && Array.isArray(deltaData.detailedSubitems)) {
        const subitemsTagged = deltaData.detailedSubitems.map(sub => ({
          ...sub,
          fileId: fileId,
          sourceFile: fileRecord.filename || sub.source_file || sub.sourceFile
        }));
        state.detailedSubitems = state.detailedSubitems.concat(subitemsTagged);
      }

      // Replay exceptions queue
      const exList = deltaData.exceptions || deltaData.exceptions_queue || [];
      if (Array.isArray(exList)) {
        state.exceptionsQueue = state.exceptionsQueue.concat(exList);
      }
    }

    state.activeFileCount = fileIds.length;
    state.isDocumentLoaded = fileIds.length > 0;
  });

  return state;
}

export function addFileDelta(fileRecord, deltaData) {
  const fileId = fileRecord.file_id || fileRecord.id || `file_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
  state.deltaLedger = state.deltaLedger || {};
  state.deltaLedger[fileId] = {
    fileRecord: { ...fileRecord, file_id: fileId },
    deltaData: deltaData,
    registeredAt: new Date().toISOString()
  };
  state.activeFileCount = Object.keys(state.deltaLedger).length;
  replayDeltaLedger();
  return fileId;
}

export function removeFileDelta(fileId) {
  state.deltaLedger = state.deltaLedger || {};
  if (state.deltaLedger[fileId]) {
    delete state.deltaLedger[fileId];
  } else {
    // Search by filename fallback
    for (const [k, v] of Object.entries(state.deltaLedger)) {
      if (v.fileRecord?.filename === fileId) {
        delete state.deltaLedger[k];
        break;
      }
    }
  }
  state.activeFileCount = Object.keys(state.deltaLedger).length;
  replayDeltaLedger();
  return state;
}

// 🔍 ESTRAZIONE DINAMICA ANNI CON DATI REALI CONTABILI
export function getActiveDataYears() {
  const activeSet = new Set();
  
  // 1. Dati dal Delta Ledger (file reali caricati)
  if (state.deltaLedger) {
    for (const entry of Object.values(state.deltaLedger)) {
      if (entry.fileRecord && Array.isArray(entry.fileRecord.detected_years)) {
        entry.fileRecord.detected_years.forEach(y => {
          const n = Number(y);
          if (!isNaN(n)) activeSet.add(n);
        });
      }
      if (entry.deltaData) {
        if (Array.isArray(entry.deltaData.detected_years)) {
          entry.deltaData.detected_years.forEach(y => {
            const n = Number(y);
            if (!isNaN(n)) activeSet.add(n);
          });
        }
        if (entry.deltaData.pivot_year) {
          const py = Number(entry.deltaData.pivot_year);
          if (!isNaN(py)) activeSet.add(py);
        }
      }
    }
  }

  // 2. Dati da fullData.records con valori effettivi non-zero
  if (state.fullData && state.fullData.records) {
    for (const [yrStr, rec] of Object.entries(state.fullData.records)) {
      const yr = Number(yrStr);
      if (isNaN(yr)) continue;
      const hasCe = rec.ce && Object.values(rec.ce).some(v => typeof v === 'number' && Math.abs(v) > 0.001);
      const hasSp = rec.sp && Object.values(rec.sp).some(v => typeof v === 'number' && Math.abs(v) > 0.001);
      if (hasCe || hasSp) {
        activeSet.add(yr);
      }
    }
  }

  // 3. Fallback se documento attivo con anni comparativi
  if (activeSet.size === 0 && state.isDocumentLoaded && Array.isArray(state.detectedComparativeYears) && state.detectedComparativeYears.length > 0) {
    state.detectedComparativeYears.forEach(y => {
      const n = Number(y);
      if (!isNaN(n)) activeSet.add(n);
    });
  }

  return Array.from(activeSet).sort((a, b) => a - b);
}

// 📅 ADAPTIVE DATA-DRIVEN TIMELINE VIEWPORT
export function getTimelineYears() {
  const dataYears = getActiveDataYears();
  const manualYears = (state.manualExpandedYears || []).map(Number).filter(y => !isNaN(y));
  let allYears = Array.from(new Set([...dataYears, ...manualYears])).sort((a, b) => a - b);

  // Fallback se nessun dato presente: mostra l'anno base corrente
  if (allYears.length === 0) {
    const y0 = state.pivotYear || (state.fullData && state.fullData.baseYear) || 2025;
    allYears = [y0];
  }

  const y0 = state.pivotYear || (dataYears.length > 0 ? dataYears[dataYears.length - 1] : allYears[0]);

  return allYears.map(yr => {
    const relOffset = yr - y0;
    const isPivot = (yr === y0);
    const isManual = manualYears.includes(yr) && !dataYears.includes(yr);
    const tag = yr <= y0 ? 'actual' : 'forecast';
    const label = isPivot ? '★ Y0' : (relOffset < 0 ? `📄 Y${relOffset}` : `📈 Y+${relOffset}`);
    return {
      year: yr,
      relOffset,
      label,
      tag,
      isPivot,
      isManual
    };
  });
}

// ➕ AGGIUNTA ANNO ON-DEMAND (Storico / Forecast)
export function addTimelineYear(year) {
  const yr = parseInt(year, 10);
  if (isNaN(yr)) return;
  state.manualExpandedYears = state.manualExpandedYears || [];
  if (!state.manualExpandedYears.includes(yr)) {
    state.manualExpandedYears.push(yr);
    state.manualExpandedYears.sort((a, b) => a - b);
  }
  const y0 = state.pivotYear || 2025;
  ensureYearRecord(yr, yr > y0 ? 'forecast' : 'actual');
  notify();
  return getTimelineYears();
}

// 🗑️ RIMOZIONE ANNO MANUALE
export function removeTimelineYear(year) {
  const yr = parseInt(year, 10);
  if (isNaN(yr) || !state.manualExpandedYears) return;
  state.manualExpandedYears = state.manualExpandedYears.filter(y => y !== yr);
  notify();
  return getTimelineYears();
}

export function setPivotYear(y0) {
  const yr = parseInt(y0, 10);
  if (!isNaN(yr)) {
    state.pivotYear = yr;
    state.fullData.baseYear = yr;
    notify();
  }
}

export function getActiveYears() {
  if (!state.fullData.records || Object.keys(state.fullData.records).length === 0) {
    return [2025, 2026, 2027, 2028, 2029];
  }
  return Object.keys(state.fullData.records).map(Number).sort((a, b) => a - b);
}

export function ensureYearRecord(year, dataType = 'actual') {
  const yr = parseInt(year, 10) || 2025;
  state.fullData.records = state.fullData.records || {};
  if (!state.fullData.records[yr]) {
    state.fullData.records[yr] = {
      year: yr,
      dataType: dataType,
      ce: Object.fromEntries(CE_KEYS.map(k => [k, 0])),
      sp: Object.fromEntries(SP_KEYS.map(k => [k, 0]))
    };
  }
  return state.fullData.records[yr];
}

export function getRecord(year) {
  const yr = parseInt(year, 10) || 2025;
  return (state.fullData.records && state.fullData.records[yr]) || null;
}

export function migrateV09ToV10(legacyData) {
  if (!legacyData) return;
  const baseYr = legacyData.baseYear || state.pivotYear || 2025;
  legacyData.records = legacyData.records || {};

  if (legacyData.ce && Array.isArray(legacyData.ce.ricaviVendite)) {
    for (let i = 0; i < 5; i++) {
      const yr = baseYr + i;
      const rec = ensureYearRecord(yr, 'actual');
      for (const key of Object.keys(rec.ce)) {
        if (legacyData.ce[key] && Array.isArray(legacyData.ce[key])) {
          rec.ce[key] = legacyData.ce[key][i] !== undefined ? legacyData.ce[key][i] : 0;
        }
      }
      for (const key of Object.keys(rec.sp)) {
        if (legacyData.sp[key] && Array.isArray(legacyData.sp[key])) {
          rec.sp[key] = legacyData.sp[key][i] !== undefined ? legacyData.sp[key][i] : 0;
        }
      }
      if (legacyData.sp.capitaleSociale !== undefined && i === 0) {
        rec.sp.capitaleSociale = parseFloat(legacyData.sp.capitaleSociale) || 0;
      }
    }
  }
}

export function setVisibleYearsCount(count) {
  const cnt = parseInt(count, 10);
  if (!isNaN(cnt) && cnt >= 1 && cnt <= 5) {
    state.visibleYearsCount = cnt;
    if (typeof document !== 'undefined') {
      [1, 2, 3, 5].forEach(n => {
        const btn = document.getElementById(`btnHz${n}`);
        if (btn) {
          if (n === cnt) {
            btn.classList.add('active-hz');
            btn.style.background = 'var(--accent-blue)';
            btn.style.color = '#ffffff';
          } else {
            btn.classList.remove('active-hz');
            btn.style.background = 'transparent';
            btn.style.color = 'var(--text-secondary)';
          }
        }
      });
    }
    notify();
  }
}

export function toggleEditMode() {
  state.editMode = !state.editMode;
  state.fsmState = state.editMode ? 'EDITING' : 'VIEWING';
  if (typeof document !== 'undefined') {
    const body = document.body;
    const btnHeader = document.getElementById('btnToggleEditMode');
    const btnToolbar = document.getElementById('btnToggleEditModeToolbar');
    if (body) {
      if (state.editMode) {
        body.classList.add('edit-mode-active');
        if (btnHeader) {
          btnHeader.classList.add('active-edit-mode');
          btnHeader.innerHTML = '<span class="btn-icon">⚡</span> Disattiva Modifica';
        }
        if (btnToolbar) {
          btnToolbar.classList.add('active-edit-mode');
          btnToolbar.innerHTML = '⚡ Disattiva Modifica';
        }
      } else {
        body.classList.remove('edit-mode-active');
        if (btnHeader) {
          btnHeader.classList.remove('active-edit-mode');
          btnHeader.innerHTML = '<span class="btn-icon">✏️</span> Modalità Modifica';
        }
        if (btnToolbar) {
          btnToolbar.classList.remove('active-edit-mode');
          btnToolbar.innerHTML = '✏️ Modalità Modifica';
        }
      }
    }
    document.querySelectorAll('.editable-label').forEach(lbl => {
      lbl.contentEditable = state.editMode ? 'true' : 'false';
    });
  }
  notify();
  return state.editMode;
}

export function resetDataToZero() {
  const currentY0 = state.pivotYear || 2025;
  state.deltaLedger = {};
  state.activeFileCount = 0;
  resetState();
  setPivotYear(currentY0);
  notify();
}
