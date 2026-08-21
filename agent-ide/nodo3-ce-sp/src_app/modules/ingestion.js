// 🏛️ INGESTION & DOCUMENT PROCESSING CONTROLLER - NODO 3 (ES6 Module)
// Multi-File Batch Ingestion, Hard File Limiter (Max 4), Delta Ledger Integration & Limbo Queue

import {
  getState, setState, ensureYearRecord, getRecord, resetDataToZero, setPivotYear,
  takeStateSnapshot, restoreStateSnapshot, addFileDelta, removeFileDelta, replayDeltaLedger
} from './state.js';
import { recalculateFinancials } from './financial_engine.js';
import { renderCETable } from './table_ce.js';
import { renderSPTables } from './table_sp.js';
import { renderKpiCards, renderCharts } from './kpi_analytics.js';
import { showToast, triggerTableFlash, showPivotYearSelectionModal } from './modals.js';
import {
  formatEuro, getCategoryGroupKey, CATEGORY_GROUP_META, getYearSelectOptions,
  getMappingSelectOptions, MAX_ACTIVE_FILES, MAX_FILE_SIZE_BYTES
} from './constants.js';

export let exceptionsQueue = [];

export function globalResetSession(force = false) {
  const state = getState();
  if (!force && state.isDocumentLoaded) {
    document.getElementById('resetConfirmModal')?.classList.add('open');
    return;
  }

  state.isDocumentLoaded = false;
  state.isComparativeEnabled = false;
  state.visibleYearsCount = 5;
  state.activeScenario = 'base';
  state.activeStressFactor = 1.0;
  state.detailedSubitems = [];
  state.hitlMappings = {};
  state.manualOverrides = {};
  state.previousYearData = null;
  state.pendingPreviousYearData = null;
  state.deltaLedger = {};
  state.activeFileCount = 0;
  state.manualExpandedYears = [];
  exceptionsQueue = [];

  resetDataToZero();
  state.uploadedFiles = [];
  state.uploadedFilesDetails = [];
  updateDocumentStatusBar([]);
  renderUploadedFilesList([]);

  const hub = document.getElementById('reconciliationHub');
  if (hub) hub.style.display = 'none';

  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  triggerTableFlash();
  showToast("🧹 Reset Globale Eseguito: Tutti i parametri azzerati a €0!", "danger");
}

export function loadSimulatedDocumentDemo() {
  const state = getState();
  const demoFileRecord = {
    file_id: "demo_bilancio_2025",
    filename: "Bilancio_Integrale_Enterprise_2025.pdf",
    file_type: "PDF",
    size_bytes: 1258291,
    extracted_items_count: 42,
    confidence_score: 0.99,
    upload_timestamp: new Date().toISOString(),
    detected_years: [2025, 2024],
    document_type: "FULL_BILANCIO"
  };

  const demoDeltaData = {
    pivot_year: 2025,
    ce: {
      ricaviVendite: [65000, 460000, 2170000, 3038000, 3949400],
      altriRicavi: [2000, 8000, 15000, 25000, 40000],
      costiMaterieHosting: [4500, 28000, 120000, 180000, 240000],
      costiServiziMarketing: [12000, 85000, 480000, 210000, 210000],
      costiGodimentoBeni: [4700, 35600, 220000, 27000, 18840],
      salariStipendi: [60000, 130000, 290000, 420000, 560000],
      oneriSociali: [17000, 40000, 90000, 135000, 180000],
      tfrQuota: [7000, 15000, 34000, 45000, 60000],
      ammImmateriali: [1000, 1000, 4000, 6000, 8000],
      ammMateriali: [2000, 2000, 6000, 9000, 12000],
      svalutazioneCrediti: [500, 1500, 5000, 8000, 10000],
      oneriDiversi: [1200, 3500, 12000, 15000, 20000],
      proventiFinanziari: [0, 500, 3000, 12000, 25000],
      oneriFinanziari: [1200, 800, 400, 0, 0]
    },
    sp: {
      capitaleSociale: 10000,
      immaterialiLorde: [5000, 8000, 20000, 32000, 48000],
      materialiLorde: [10000, 19000, 35000, 50000, 65000],
      finanziarieDepositi: [2000, 4000, 6000, 8000, 10000],
      creditiClienti: [8500, 38000, 140000, 190000, 240000],
      creditiTributari: [1500, 4500, 12000, 18000, 25000],
      cassa: [15000, 44856, 711213, 2174943, 4119746],
      riservaLegale: [0, 4918, 37820, 108534, 202310],
      riserveUtili: [0, -43200, 55156, 713213, 2127483],
      fondiRischi: [1000, 3000, 8000, 15000, 25000],
      tfrFondo: [7000, 22000, 56000, 101000, 161000],
      debBanche: [55200, 0, 0, 0, 0],
      debFornitori: [3500, 18000, 68000, 35000, 39000],
      debTrib: [0, 21344, 254643, 547270, 725757],
      debPrev: [2500, 6500, 15000, 22000, 30000]
    },
    detailedSubitems: []
  };

  addFileDelta(demoFileRecord, demoDeltaData);
  recalculateFinancials();

  if (typeof document !== 'undefined') {
    updateDocumentStatusBar(state.uploadedFiles);
    renderUploadedFilesList(state.uploadedFiles);
    renderCETable();
    renderSPTables();
    renderKpiCards();
    renderCharts();
    triggerTableFlash();
    showToast("📄 Documento Demo Ingestito con Successo: Tutti i parametri estratti!", "success");
  }
}

export function removeUploadedFile(idx) {
  const state = getState();
  if (!state.uploadedFiles || idx < 0 || idx >= state.uploadedFiles.length) return;

  const removedName = state.uploadedFiles[idx];
  const fileDetail = state.uploadedFilesDetails && state.uploadedFilesDetails[idx];
  const fileId = fileDetail?.id || removedName;

  removeFileDelta(fileId);
  recalculateFinancials();

  if (state.uploadedFiles.length === 0) {
    state.isDocumentLoaded = false;
    showToast(`🗑️ Rimosso ${removedName}. Workspace svuotato (€0).`, "info");
  } else {
    showToast(`🗑️ Rimosso file: ${removedName}. Ricalcolo deterministico completato.`, "info");
  }

  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  updateDocumentStatusBar(state.uploadedFiles);
  renderUploadedFilesList(state.uploadedFiles);
}

export function renderUploadedFilesList(files = []) {
  const container = document.getElementById('fileItemsContainer');
  const wrapper = document.getElementById('uploadedFilesList');
  const dropzone = document.getElementById('dropzone');
  if (!container || !wrapper) return;

  if (!files || files.length === 0) {
    wrapper.style.display = 'none';
    container.innerHTML = '';
    container.classList.remove('compact-badge-grid');
    if (dropzone) {
      dropzone.className = 'dropzone';
      dropzone.innerHTML = `
        <div class="dropzone-icon">📤</div>
        <h3>Trascina qui da 1 a 4 file ERP (PDF / ODS / ODT / Word / Excel / CSV / XML FatturaPA)</h3>
        <p>Oppure fai clic su questo riquadro per aprire la finestra di selezione dei file</p>
        <div style="margin-top: 1rem;">
          <button class="btn btn-amber" onclick="event.stopPropagation(); window.triggerFileBrowser();">
            📂 Seleziona File dal Disco
          </button>
        </div>
      `;
    }
    return;
  }

  wrapper.style.display = 'block';
  container.className = 'file-items-container compact-badge-grid';

  const state = getState();
  let html = '';
  files.forEach((name, idx) => {
    const detail = (state.uploadedFilesDetails && state.uploadedFilesDetails[idx]) || {};
    html += `
      <div class="file-badge-card" style="display: flex; align-items: center; justify-content: space-between; background: rgba(15, 23, 42, 0.7); border: 1px solid var(--border-color); border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 0.5rem;">
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <span style="font-size: 1.2rem;">📄</span>
          <div>
            <strong style="font-size: 0.85rem; color: var(--text-main); display: block;">${name}</strong>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${detail.type || 'ERP Doc'} | ${detail.paramsCount || 0} parametri estratti</span>
          </div>
        </div>
        <button class="btn btn-xs btn-outline-danger" onclick="window.removeUploadedFile(${idx})" title="Rimuovi file">
          ✕
        </button>
      </div>
    `;
  });

  container.innerHTML = html;
}

export function updateDocumentStatusBar(files = []) {
  const bar = document.getElementById('docStatusBar');
  const txt = document.getElementById('docStatusText');
  if (!bar || !txt) return;

  if (files && files.length > 0) {
    bar.style.display = 'flex';
    txt.innerHTML = `<strong>${files.length} Documenti Attivi:</strong> ${files.join(', ')}`;
  } else {
    bar.style.display = 'none';
  }
}

export function triggerFileBrowser() {
  const input = document.getElementById('fileInput') || document.getElementById('fileInputHidden');
  if (input) input.click();
}

export function handleFileSelect(event) {
  const files = event.target.files;
  if (files && files.length > 0) {
    processUserUploadedFiles(Array.from(files));
  }
  event.target.value = '';
}

export async function processUserUploadedFiles(fileList, selectedYear = null) {
  const state = getState();
  if (state.isProcessingFiles) {
    showToast("⚠️ Ingestione file già in corso... Attendere il completamento.", "warning");
    return;
  }

  // 1. Hard File Limiter Guard cumulativo (Max 4 active files)
  const currentActive = state.activeFileCount || Object.keys(state.deltaLedger || {}).length;
  const incomingCount = fileList.length;

  if (incomingCount > MAX_ACTIVE_FILES || (currentActive + incomingCount) > MAX_ACTIVE_FILES) {
    showToast(`⛔ Hard File Limiter Guard violato: Massimo ${MAX_ACTIVE_FILES} file attivi contemporaneamente (Attivi: ${currentActive}, Tentativo: +${incomingCount}). Rimuovere un file prima di aggiungerne altri.`, "error");
    return;
  }

  // 2. File Size Guard (50MB Max per file)
  for (const file of fileList) {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      showToast(`⛔ File '${file.name}' supera la dimensione massima di 50MB (${(file.size / (1024 * 1024)).toFixed(1)}MB > 50MB). Ingestione bloccata.`, "error");
      return;
    }
  }

  // 3. Pre-batch Snapshot for All-or-Nothing Rollback
  const preBatchSnapshot = takeStateSnapshot();

  let targetYear = selectedYear;
  if (!targetYear) {
    const yearSelect = document.getElementById('uploadYearSelector');
    targetYear = yearSelect ? (parseInt(yearSelect.value, 10) || 2025) : 2025;
  }

  state.isProcessingFiles = true;

  try {
    const formData = new FormData();
    for (let i = 0; i < fileList.length; i++) {
      formData.append('files', fileList[i]);
    }
    formData.append('year', targetYear);
    formData.append('current_active_count', currentActive);

    const hostName = (typeof window !== 'undefined' && window.location.hostname) || '127.0.0.1';
    const response = await fetch(`http://${hostName}:8000/api/v1/ingest/multi_file`, {
      method: 'POST',
      body: formData
    });

    if (response.ok) {
      const result = await response.json();

      if (result.is_success && result.ingested_files) {
        state.manualExpandedYears = [];
        // Register each file record and its delta into deltaLedger
        for (const fileRecord of result.ingested_files) {
          const deltaData = {
            pivot_year: targetYear,
            ce: result.combined_extracted_data?.ce || {},
            sp: result.combined_extracted_data?.sp || {},
            detailedSubitems: (result.combined_extracted_data?.detailedSubitems || []).filter(
              sub => sub.file_id === fileRecord.file_id || sub.source_file === fileRecord.filename
            ),
            exceptions: (result.exceptions_queue || []).filter(
              ex => ex.source_file === fileRecord.filename
            )
          };
          addFileDelta(fileRecord, deltaData);
        }

        if (result.exceptions_queue && Array.isArray(result.exceptions_queue)) {
          exceptionsQueue = result.exceptions_queue;
          renderExceptions(exceptionsQueue);
        }

        state.pivotYear = targetYear;
        state.isDocumentLoaded = true;

        recalculateFinancials();
        renderCETable();
        renderSPTables();
        renderKpiCards();
        renderCharts();
        triggerTableFlash();
        updateDocumentStatusBar(state.uploadedFiles);
        renderUploadedFilesList(state.uploadedFiles);

        showToast(`✓ Ingestione multi-file completata con successo: ${fileList.length} file elaborati!`, "success");
      }
    } else {
      const errorData = await response.json().catch(() => ({}));
      const errorMsg = errorData.detail || `Errore HTTP ${response.status}`;
      restoreStateSnapshot(preBatchSnapshot);
      showToast(`❌ Errore Backend Ingestione: ${errorMsg}`, "error");
    }
  } catch (apiErr) {
    console.warn("Backend API multi-file ingestion error:", apiErr);
    restoreStateSnapshot(preBatchSnapshot);
    showToast(`⚠️ Impossibile comunicare con il Server Backend (127.0.0.1:8000). Ripristinato lo stato precedente.`, "warning");
  } finally {
    state.isProcessingFiles = false;
  }
}

// 🏛️ LIMBO QUEUE RECONCILIATION RENDERING & ACTIONS
export function renderExceptions(queue = []) {
  const container = document.getElementById('exceptionsQueueContainer') || document.getElementById('exceptionsTableContainer');
  const hub = document.getElementById('reconciliationHub');
  if (!hub || !container) return;

  if (queue.length === 0) {
    container.style.display = 'none';
    hub.style.display = 'none';
    return;
  }

  hub.style.display = 'block';
  container.style.display = 'block';

  const totalCount = queue.length;
  const totalSum = queue.reduce((acc, ex) => acc + (parseFloat(ex.amount) || 0), 0);
  const selectedCount = queue.filter(ex => ex.selected).length;
  const allSelected = totalCount > 0 && selectedCount === totalCount;

  const grouped = {};
  queue.forEach(ex => {
    if (!ex.id) ex.id = 'ex_' + Math.random().toString(36).substr(2, 9);
    const gKey = getCategoryGroupKey(ex.suggested_mapping || 'altriRicavi');
    if (!grouped[gKey]) grouped[gKey] = [];
    grouped[gKey].push(ex);
  });

  let html = `
    <div class="limbo-batch-toolbar">
      <div style="display: flex; align-items: center; gap: 1rem;">
        <label style="font-size: 0.82rem; font-weight: 600; color: var(--text-main); display: inline-flex; align-items: center; gap: 0.45rem; cursor: pointer;">
          <input type="checkbox" id="selectAllExceptions" ${allSelected ? 'checked' : ''} onchange="window.toggleSelectAllExceptions(this.checked)" style="transform: scale(1.1); cursor: pointer;">
          <span>Seleziona Tutti (${totalCount})</span>
        </label>
        <span style="font-size: 0.8rem; color: var(--text-muted);">| Totale Limbo Queue: <strong style="color: var(--accent-emerald); font-family: var(--font-mono);">${formatEuro(totalSum)}</strong></span>
      </div>

      <div style="display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap;">
        <button class="btn btn-sm btn-outline-success" onclick="window.approveSelectedExceptions()" ${selectedCount === 0 ? 'disabled style="opacity:0.5; cursor:not-allowed;"' : ''}>
          ✓ Approva Selezionati (${selectedCount})
        </button>
        <button class="btn btn-sm btn-emerald" onclick="window.approveAllExceptions()">
          ⚡ Approva Tutti i Suggerimenti IA (${totalCount} Voci)
        </button>
      </div>
    </div>
  `;

  for (const gKey in grouped) {
    const groupItems = grouped[gKey];
    const groupSum = groupItems.reduce((acc, i) => acc + (parseFloat(i.amount) || 0), 0);
    const meta = CATEGORY_GROUP_META[gKey] || CATEGORY_GROUP_META.altre;

    let rowsHTML = '';
    groupItems.forEach(ex => {
      const id = ex.id;
      const curMap = ex.suggested_mapping || 'altriRicavi';
      const curYr = ex.year || 2025;
      const amt = parseFloat(ex.amount) || 0;
      const rawDesc = (ex.description || 'Voce da Mappare').replace(/^(?:Voce\s+(?:ODS\s+)?da\s+classificare:\s*)/i, '').trim();
      const descStr = rawDesc.replace(/"/g, '&quot;');

      rowsHTML += `
        <tr id="ex_row_${id}">
          <td style="width: 36px; text-align: center;">
            <input type="checkbox" ${ex.selected ? 'checked' : ''} onchange="window.toggleItemSelection('${id}', this.checked)" style="cursor: pointer;">
          </td>
          <td style="min-width: 180px;">
            <input type="text" id="desc_${id}" value="${descStr}" onchange="window.updateExceptionItem('${id}', 'description', this.value)" style="width: 100%; background: var(--bg-input); color: var(--text-main); border: 1px solid var(--border-color); border-radius: 4px; font-size: 0.8rem; padding: 3px 6px;">
          </td>
          <td style="width: 105px;">
            <select id="year_${id}" onchange="window.updateExceptionItem('${id}', 'year', this.value)" style="width: 100%; background: var(--bg-input); color: var(--text-main); border: 1px solid var(--border-color); border-radius: 4px; font-size: 0.8rem; padding: 3px 4px;">
              ${getYearSelectOptions(curYr)}
            </select>
          </td>
          <td style="width: 130px;">
            <input type="number" step="0.01" id="amount_${id}" value="${amt}" onchange="window.updateExceptionItem('${id}', 'amount', this.value)" style="width: 100%; background: var(--bg-input); color: var(--text-main); border: 1px solid var(--border-color); border-radius: 4px; font-size: 0.8rem; padding: 3px 6px;">
          </td>
          <td style="min-width: 200px;">
            <select id="map_${id}" onchange="window.reassignExceptionCategory('${id}', this.value)" style="width: 100%; background: var(--bg-input); color: var(--text-main); border: 1px solid var(--border-color); border-radius: 4px; font-size: 0.8rem; padding: 3px 4px;">
              ${getMappingSelectOptions(curMap)}
            </select>
          </td>
          <td style="width: 110px; text-align: center;">
            <button class="btn btn-xs btn-success" onclick="window.approveException('${id}')" title="Approva voce singola">
              ✓ Mappa
            </button>
          </td>
        </tr>
      `;
    });

    html += `
      <div class="limbo-accordion-group" id="group_${gKey}">
        <div class="limbo-accordion-header" onclick="window.toggleLimboAccordion('${gKey}')">
          <div style="display: flex; align-items: center; gap: 0.65rem;">
            <span class="accordion-arrow" id="arrow_${gKey}">▼</span>
            <strong style="font-size: 0.88rem; color: var(--text-main);">${meta.title}</strong>
            <span class="badge" style="background: rgba(99, 102, 241, 0.2); color: var(--accent-blue); font-size: 0.72rem;">${groupItems.length} Voci</span>
            <span class="badge" style="background: rgba(16, 185, 129, 0.2); color: var(--accent-emerald); font-size: 0.72rem; font-family: var(--font-mono);">${formatEuro(groupSum)}</span>
          </div>
          <button class="btn btn-xs btn-emerald" onclick="event.stopPropagation(); window.approveGroupExceptions('${gKey}')" title="Approva tutte le voci di questo gruppo">
            ⚡ Approva Questo Gruppo (${groupItems.length})
          </button>
        </div>
        <div class="limbo-accordion-body" id="body_${gKey}" style="display: block;">
          <table class="table limbo-table" style="width: 100%; font-size: 0.85rem;">
            <thead>
              <tr>
                <th style="width: 36px; text-align: center;">
                  <input type="checkbox" onchange="window.toggleGroupSelectAll('${gKey}', this.checked)" title="Seleziona tutti in questo gruppo" style="cursor: pointer;">
                </th>
                <th style="min-width: 180px;">Descrizione Voce</th>
                <th style="width: 105px;">Anno Target</th>
                <th style="width: 130px;">Valore (€)</th>
                <th style="min-width: 200px;">Macro-Gruppo / Destinazione</th>
                <th style="width: 110px; text-align: center;">Azione</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHTML}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  container.innerHTML = html;
}

export function approveException(id) {
  const exIndex = exceptionsQueue.findIndex(e => e.id === id);
  if (exIndex > -1) {
    const ex = exceptionsQueue[exIndex];
    const amtInput = document.getElementById(`amount_${id}`);
    const yrSelect = document.getElementById(`year_${id}`);
    const mapSelect = document.getElementById(`map_${id}`);
    const descInput = document.getElementById(`desc_${id}`);

    const amount = amtInput ? (parseFloat(amtInput.value) || 0) : (ex.amount || 0);
    const year = yrSelect ? (parseInt(yrSelect.value, 10) || 2025) : (parseInt(ex.year, 10) || 2025);
    const mapping = mapSelect ? mapSelect.value : (ex.suggested_mapping || 'altriRicavi');
    const desc = descInput ? descInput.value : (ex.description || 'Voce Mappata');

    const rec = ensureYearRecord(year);
    if (rec.ce[mapping] !== undefined) {
      rec.ce[mapping] += amount;
    } else if (rec.sp[mapping] !== undefined) {
      rec.sp[mapping] += amount;
    } else {
      rec.ce[mapping] = (rec.ce[mapping] || 0) + amount;
    }

    const state = getState();
    state.hitlMappings = state.hitlMappings || {};
    state.hitlMappings[mapping] = {
      file: ex.file || (state.uploadedFiles && state.uploadedFiles[0]) || 'Limbo Queue',
      path: `Mappatura Manuale Limbo Queue (${desc})`,
      type: 'Mappatura Limbo HITL 🤖'
    };

    exceptionsQueue.splice(exIndex, 1);
    renderExceptions(exceptionsQueue);
    recalculateFinancials();
    renderCETable();
    renderSPTables();
    renderKpiCards();
    renderCharts();
    triggerTableFlash();
    showToast(`✓ '${desc}' mappata su ${mapping} (Anno ${year}): +${formatEuro(amount)}`, "success");
  }
}

export function approveAllExceptions() {
  if (!exceptionsQueue || exceptionsQueue.length === 0) return;
  const count = exceptionsQueue.length;
  const state = getState();

  const queueToProcess = [...exceptionsQueue];
  queueToProcess.forEach(ex => {
    const amount = parseFloat(ex.amount) || 0;
    const year = parseInt(ex.year, 10) || 2025;
    const mapping = ex.suggested_mapping || 'altriRicavi';
    const desc = ex.description || 'Voce Mappata';

    const rec = ensureYearRecord(year);
    if (rec.ce[mapping] !== undefined) {
      rec.ce[mapping] += amount;
    } else if (rec.sp[mapping] !== undefined) {
      rec.sp[mapping] += amount;
    } else {
      rec.ce[mapping] = (rec.ce[mapping] || 0) + amount;
    }

    state.hitlMappings = state.hitlMappings || {};
    state.hitlMappings[mapping] = {
      file: ex.file || (state.uploadedFiles && state.uploadedFiles[0]) || 'Limbo Queue',
      path: `Mappatura Batch Limbo Queue (${desc})`,
      type: 'Mappatura Limbo HITL 🤖'
    };
  });

  exceptionsQueue = [];
  renderExceptions(exceptionsQueue);
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  triggerTableFlash();
  showToast(`⚡ Approvate in 1-Click tutte le ${count} voci della Limbo Queue!`, "success");
}

export function approveSelectedExceptions() {
  const selectedItems = exceptionsQueue.filter(ex => ex.selected);
  if (selectedItems.length === 0) {
    showToast("⚠️ Seleziona almeno una voce con la checkbox per approvare!", "warning");
    return;
  }
  selectedItems.forEach(ex => approveException(ex.id));
}

export function approveGroupExceptions(gKey) {
  const groupItems = exceptionsQueue.filter(ex => getCategoryGroupKey(ex.suggested_mapping || 'altriRicavi') === gKey);
  if (groupItems.length === 0) return;

  const count = groupItems.length;
  const state = getState();

  groupItems.forEach(ex => {
    const exIndex = exceptionsQueue.findIndex(e => e.id === ex.id);
    if (exIndex > -1) {
      const amount = parseFloat(ex.amount) || 0;
      const year = parseInt(ex.year, 10) || 2025;
      const mapping = ex.suggested_mapping || 'altriRicavi';
      const desc = ex.description || 'Voce Mappata';

      const rec = ensureYearRecord(year);
      if (rec.ce[mapping] !== undefined) {
        rec.ce[mapping] += amount;
      } else if (rec.sp[mapping] !== undefined) {
        rec.sp[mapping] += amount;
      } else {
        rec.ce[mapping] = (rec.ce[mapping] || 0) + amount;
      }

      state.hitlMappings = state.hitlMappings || {};
      state.hitlMappings[mapping] = {
        file: ex.file || (state.uploadedFiles && state.uploadedFiles[0]) || 'Limbo Queue',
        path: `Mappatura Gruppo Limbo Queue (${desc})`,
        type: 'Mappatura Limbo HITL 🤖'
      };

      exceptionsQueue.splice(exIndex, 1);
    }
  });

  renderExceptions(exceptionsQueue);
  recalculateFinancials();
  renderCETable();
  renderSPTables();
  renderKpiCards();
  renderCharts();
  triggerTableFlash();
  showToast(`⚡ Approvate tutte le ${count} voci del gruppo selezionato!`, "success");
}

export function reassignExceptionCategory(id, newMapping) {
  const ex = exceptionsQueue.find(e => e.id === id);
  if (ex) {
    ex.suggested_mapping = newMapping;
    const amtInput = document.getElementById(`amount_${id}`);
    const yrSelect = document.getElementById(`year_${id}`);
    const descInput = document.getElementById(`desc_${id}`);
    if (amtInput) ex.amount = parseFloat(amtInput.value) || 0;
    if (yrSelect) ex.year = parseInt(yrSelect.value, 10) || 2025;
    if (descInput) ex.description = descInput.value;

    renderExceptions(exceptionsQueue);
    showToast("📌 Voce riassegnata al nuovo Macro-Gruppo!", "info");
  }
}

export function updateExceptionItem(id, field, value) {
  const ex = exceptionsQueue.find(e => e.id === id);
  if (ex) {
    if (field === 'description') ex.description = value;
    if (field === 'year') ex.year = parseInt(value, 10) || 2025;
    if (field === 'amount') ex.amount = parseFloat(value) || 0;
  }
}

export function toggleSelectAllExceptions(isChecked) {
  exceptionsQueue.forEach(ex => { ex.selected = isChecked; });
  renderExceptions(exceptionsQueue);
}

export function toggleGroupSelectAll(gKey, isChecked) {
  exceptionsQueue.forEach(ex => {
    if (getCategoryGroupKey(ex.suggested_mapping || 'altriRicavi') === gKey) {
      ex.selected = isChecked;
    }
  });
  renderExceptions(exceptionsQueue);
}

export function toggleItemSelection(id, isChecked) {
  const ex = exceptionsQueue.find(e => e.id === id);
  if (ex) {
    ex.selected = isChecked;
    renderExceptions(exceptionsQueue);
  }
}

export function toggleLimboAccordion(gKey) {
  const body = document.getElementById(`body_${gKey}`);
  const arrow = document.getElementById(`arrow_${gKey}`);
  if (body) {
    if (body.style.display === 'none') {
      body.style.display = 'block';
      if (arrow) arrow.className = 'accordion-arrow';
    } else {
      body.style.display = 'none';
      if (arrow) arrow.className = 'accordion-arrow collapsed';
    }
  }
}
