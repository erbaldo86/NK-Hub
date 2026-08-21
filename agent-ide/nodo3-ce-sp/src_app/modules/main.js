// 🏛️ MAIN ENTRYPOINT - NODO 3 (ES6 Modular Hub)
// Nexus Keystone 3.0 Standard - Modular ES6 Architecture

import * as Constants from './constants.js';
import * as State from './state.js';
import * as FinancialEngine from './financial_engine.js';
import * as TableCE from './table_ce.js';
import * as TableSP from './table_sp.js';
import * as KPIAnalytics from './kpi_analytics.js';
import * as Modals from './modals.js';
import * as Ingestion from './ingestion.js';
import * as ExportEngine from './export_engine.js';

// Expose modules and helper functions to global window for HTML inline handlers
window.NK_MODULES = {
  Constants,
  State,
  FinancialEngine,
  TableCE,
  TableSP,
  KPIAnalytics,
  Modals,
  Ingestion,
  ExportEngine
};

// 🌐 Window Global API Binds (100% Backwards Compatible with index.html)
window.state = State.getState();
window.getState = State.getState;
window.setState = State.setState;
window.getTimelineYears = State.getTimelineYears;
window.setPivotYear = State.setPivotYear;
window.ensureYearRecord = State.ensureYearRecord;
window.getRecord = State.getRecord;
window.setVisibleYearsCount = (count) => {
  State.setVisibleYearsCount(count);
  TableCE.renderCETable();
  TableSP.renderSPTables();
};
window.toggleEditMode = State.toggleEditMode;
window.resetDataToZero = () => {
  State.resetDataToZero();
  FinancialEngine.recalculateFinancials();
  TableCE.renderCETable();
  TableSP.renderSPTables();
  KPIAnalytics.renderKpiCards();
  KPIAnalytics.renderCharts();
};
window.migrateV09ToV10 = State.migrateV09ToV10;

// State Snapshot, Batch & Delta Ledger Replay Engine
window.takeStateSnapshot = State.takeStateSnapshot;
window.restoreStateSnapshot = State.restoreStateSnapshot;
window.batchUpdate = State.batchUpdate;
window.replayDeltaLedger = State.replayDeltaLedger;
window.addFileDelta = State.addFileDelta;
window.removeFileDelta = State.removeFileDelta;
window.getActiveDataYears = State.getActiveDataYears;

// Adaptive Timeline & On-Demand Column Expansion
window.addTimelineYear = (yr) => {
  State.addTimelineYear(yr);
  FinancialEngine.recalculateFinancials();
  TableCE.renderCETable();
  TableSP.renderSPTables();
  KPIAnalytics.renderKpiCards();
  KPIAnalytics.renderCharts();
  Modals.showToast(`➕ Aggiunta colonna ${yr} al modello!`, 'success');
};

window.removeTimelineYear = (yr) => {
  State.removeTimelineYear(yr);
  FinancialEngine.recalculateFinancials();
  TableCE.renderCETable();
  TableSP.renderSPTables();
  KPIAnalytics.renderKpiCards();
  KPIAnalytics.renderCharts();
  Modals.showToast(`🗑️ Rimossa colonna ${yr} dal modello.`, 'info');
};

window.promptAddTimelineYear = () => {
  const timeline = State.getTimelineYears();
  const years = timeline.map(t => t.year);
  const maxYear = years.length > 0 ? Math.max(...years) : 2025;
  const minYear = years.length > 0 ? Math.min(...years) : 2025;
  const nextForecast = maxYear + 1;
  const prevHistorical = minYear - 1;

  const choice = prompt(
    `➕ Aggiungi Colonna Anno:\n` +
    `1. Digita "${nextForecast}" per aggiungere il prossimo anno di previsione (Forecast)\n` +
    `2. Digita "${prevHistorical}" per aggiungere l'anno precedente (Storico)\n` +
    `Oppure inserisci qualsiasi anno numerico desiderato:`,
    nextForecast
  );

  if (choice !== null && choice.trim() !== '') {
    const yr = parseInt(choice.trim(), 10);
    if (!isNaN(yr) && yr >= 2000 && yr <= 2100) {
      if (years.includes(yr)) {
        Modals.showToast(`⚠️ L'anno ${yr} è già presente nel modello!`, 'warning');
        return;
      }
      window.addTimelineYear(yr);
    } else {
      Modals.showToast("⚠️ Inserisci un anno valido a 4 cifre (es. 2026)!", "warning");
    }
  }
};

// Financial Engine
window.recalculateFinancials = FinancialEngine.recalculateFinancials;
window.recalculateMacroFromSubitems = FinancialEngine.recalculateMacroFromSubitems;
window.balanceSPQuickFix = FinancialEngine.balanceSPQuickFix;
window.setScenario = FinancialEngine.setScenario;
window.setStressTestFactor = FinancialEngine.setStressTestFactor;
window.setAtecoSector = FinancialEngine.setAtecoSector;

// Tables
window.renderCETable = TableCE.renderCETable;
window.renderSPTables = TableSP.renderSPTables;
window.openDetailedSubitemsModal = TableCE.openDetailedSubitemsModal;
window.closeDetailedSubitemsModal = TableCE.closeDetailedSubitemsModal;
window.insertManualSubitem = TableCE.insertManualSubitem;
window.updateManualCategoryOptions = TableCE.updateManualCategoryOptions;
window.editFullField = TableCE.editFullField;
window.deleteSubitem = Modals.deleteSubitem;

// KPI & Analytics
window.renderKpiCards = KPIAnalytics.renderKpiCards;
window.renderCharts = KPIAnalytics.renderCharts;
window.setTopKpiSelectedYear = KPIAnalytics.setTopKpiSelectedYear;
window.setSidebarSelectedYear = KPIAnalytics.setSidebarSelectedYear;
window.renderSaasMetrics = KPIAnalytics.renderSaasMetrics;
window.updateBenchmarkInfo = KPIAnalytics.updateBenchmarkInfo;

// Modals & UI
window.showToast = Modals.showToast;
window.triggerTableFlash = Modals.triggerTableFlash;
window.openExportModal = Modals.openExportModal;
window.closeExportModal = Modals.closeExportModal;
window.openConflictModal = Modals.openConflictModal;
window.closeConflictModal = Modals.closeConflictModal;
window.resolveConflict = Modals.resolveConflict;
window.openGatewayModal = Modals.openGatewayModal;
window.closeGatewayModal = Modals.closeGatewayModal;
window.openFormulaModal = Modals.openFormulaModal;
window.closeFormulaModal = Modals.closeFormulaModal;
window.toggleGuidaDrawer = Modals.toggleGuidaDrawer;
window.openGuidaModal = Modals.openGuidaModal;
window.closeGuidaModal = Modals.closeGuidaModal;
window.switchGuidaTab = Modals.switchGuidaTab;
window.quickFixCapitaleSociale = Modals.quickFixCapitaleSociale;
window.editCapitaleSociale = Modals.editCapitaleSociale;
window.openResetConfirmModal = Modals.openResetConfirmModal;
window.closeResetConfirmModal = Modals.closeResetConfirmModal;
window.confirmGlobalReset = Modals.confirmGlobalReset;
window.closeOverwriteConfirmModal = Modals.closeOverwriteConfirmModal;
window.switchTab = Modals.switchTab;
window.togglePrivacyShield = Modals.togglePrivacyShield;
window.toggleGodMode = Modals.toggleGodMode;
window.showComparativeYearModal = Modals.showComparativeYearModal;
window.closeComparativeYearModal = Modals.closeComparativeYearModal;
window.enableComparativeMode = Modals.enableComparativeMode;
window.dismissComparativeMode = Modals.dismissComparativeMode;
window.showPivotYearSelectionModal = Modals.showPivotYearSelectionModal;
window.selectPivotOption = Modals.selectPivotOption;
window.closePivotYearSelectionModal = Modals.closePivotYearSelectionModal;
window.confirmPivotYearSelection = Modals.confirmPivotYearSelection;

// Ingestion & Reconciliation
window.globalResetSession = Ingestion.globalResetSession;
window.loadSimulatedDocumentDemo = Ingestion.loadSimulatedDocumentDemo;
window.simulateFileUpload = Ingestion.loadSimulatedDocumentDemo;
window.removeUploadedFile = Ingestion.removeUploadedFile;
window.renderUploadedFilesList = Ingestion.renderUploadedFilesList;
window.updateDocumentStatusBar = Ingestion.updateDocumentStatusBar;
window.triggerFileBrowser = Ingestion.triggerFileBrowser;
window.handleFileSelect = Ingestion.handleFileSelect;
window.processUserUploadedFiles = Ingestion.processUserUploadedFiles;
window.renderExceptions = Ingestion.renderExceptions;
window.approveException = Ingestion.approveException;
window.approveAllExceptions = Ingestion.approveAllExceptions;
window.approveSelectedExceptions = Ingestion.approveSelectedExceptions;
window.approveGroupExceptions = Ingestion.approveGroupExceptions;
window.toggleSelectAllExceptions = Ingestion.toggleSelectAllExceptions;
window.toggleGroupSelectAll = Ingestion.toggleGroupSelectAll;
window.toggleItemSelection = Ingestion.toggleItemSelection;
window.toggleLimboAccordion = Ingestion.toggleLimboAccordion;
window.reassignExceptionCategory = Ingestion.reassignExceptionCategory;
window.updateExceptionItem = Ingestion.updateExceptionItem;

// Export Engine
window.triggerDownload = ExportEngine.triggerDownload;

// Formatters
window.formatEuro = Constants.formatEuro;
window.formatPercent = Constants.formatPercent;

// Dropzone Initialization Helper
function setupDropzone() {
  const dropzone = document.getElementById('dropzone');
  if (!dropzone) return;

  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, false);
    document.body.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
    }, false);
  });

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => {
      dropzone.style.borderColor = 'var(--accent-amber)';
      dropzone.style.background = 'rgba(245, 158, 11, 0.15)';
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, () => {
      dropzone.style.borderColor = '';
      dropzone.style.background = '';
    }, false);
  });

  dropzone.addEventListener('drop', async (e) => {
    const dt = e.dataTransfer;
    const files = dt ? dt.files : null;
    if (files && files.length > 0) {
      const fileList = Array.from(files).slice(0, 4);
      await Ingestion.processUserUploadedFiles(fileList);
    }
  }, false);
}

// Global Application Bootstrap
export function bootstrap() {
  setupDropzone();
  State.setVisibleYearsCount(State.getState().visibleYearsCount || 5);
  FinancialEngine.recalculateFinancials();
  TableCE.renderCETable();
  TableSP.renderSPTables();
  KPIAnalytics.renderKpiCards();
  KPIAnalytics.renderCharts();
  KPIAnalytics.updateBenchmarkInfo();

  if (typeof window !== 'undefined' && window.mermaid) {
    try {
      window.mermaid.initialize({ startOnLoad: true, theme: 'dark' });
    } catch (err) {
      console.warn("Mermaid init warning:", err);
    }
  }

  if (typeof window !== 'undefined') {
    window.addEventListener('resize', () => {
      KPIAnalytics.renderCharts();
    });
  }
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
}
