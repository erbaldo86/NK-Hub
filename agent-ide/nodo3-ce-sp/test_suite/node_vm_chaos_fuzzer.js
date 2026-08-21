/**
 * node_vm_chaos_fuzzer.js
 * In-Memory VM Chaos Fuzzer & State Inspector (Zero-Dependency, Ultra-Fast)
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');
const os = require('os');
const { evaluateInvariants } = require('./invariant_oracle_engine');

const CONFIG = {
  totalIterations: parseInt(process.env.FUZZ_ITERATIONS || '1000', 10),
  batchSize: 200,
  ringBufferCap: 50,
  reportPath: path.resolve(__dirname, 'test_reports', 'diagnostic_report.json')
};

// Circular Ring Buffer
class RingBuffer {
  constructor(capacity) {
    this.capacity = capacity;
    this.buffer = [];
  }
  push(item) {
    if (this.buffer.length >= this.capacity) this.buffer.shift();
    this.buffer.push(item);
  }
  toArray() {
    return [...this.buffer];
  }
}

// Simulatore DOM robusto e completo per app.js
function createMockDomEnvironment() {
  const elements = new Map();

  const mockElement = (id = '', tagName = 'div') => {
    const el = {
      id,
      tagName: tagName.toUpperCase(),
      dataset: {},
      options: [],
      classList: {
        add: () => {},
        remove: () => {},
        contains: () => false,
        toggle: () => {}
      },
      style: {},
      innerHTML: '',
      innerText: '',
      textContent: '',
      value: '',
      children: [],
      appendChild: function(child) {
        if (child) {
          child.parentNode = this;
          this.children.push(child);
        }
        return child;
      },
      removeChild: function(child) {
        const idx = this.children.indexOf(child);
        if (idx !== -1) {
          this.children.splice(idx, 1);
          child.parentNode = null;
        }
        return child;
      },
      parentNode: null,
      querySelectorAll: (sel) => [mockElement('', 'div')],
      querySelector: (sel) => mockElement('', 'div'),
      closest: (sel) => mockElement('', 'div'),
      addEventListener: () => {},
      removeEventListener: () => {},
      getAttribute: (attr) => el.dataset[attr] || null,
      setAttribute: (attr, val) => { el.dataset[attr] = val; },
      focus: () => {},
      blur: () => {}
    };
    return el;
  };

  const getOrCreate = (id) => {
    if (!elements.has(id)) elements.set(id, mockElement(id));
    return elements.get(id);
  };

  const documentMock = {
    getElementById: (id) => getOrCreate(id),
    querySelector: (sel) => mockElement('', 'div'),
    querySelectorAll: (sel) => [mockElement('table-container', 'div'), mockElement('table-container-2', 'div')],
    createElement: (tag) => mockElement('', tag),
    body: mockElement('body', 'body'),
    addEventListener: () => {},
    removeEventListener: () => {}
  };

  const windowMock = {
    document: documentMock,
    console: {
      log: () => {},
      warn: () => {},
      error: (...args) => {},
      info: () => {}
    },
    setTimeout: (fn, ms) => 1,
    clearTimeout: () => {},
    setInterval: () => 1,
    clearInterval: () => {},
    requestAnimationFrame: (cb) => { if (typeof cb === 'function') cb(); },
    getComputedStyle: () => ({ display: 'block', visibility: 'visible' }),
    fetch: async () => ({ json: async () => ({}) }),
    __TEST_HARNESS__: true
  };

  windowMock.window = windowMock;
  windowMock.global = windowMock;

  return { windowMock, documentMock };
}

function pickWeightedAction() {
  const rand = Math.random() * 100;
  if (rand < 35) return 'EDIT_CE_CELL';
  if (rand < 70) return 'EDIT_SP_CELL';
  if (rand < 80) return 'ADD_SUBITEM';
  if (rand < 88) return 'CHANGE_PIVOT_YEAR';
  if (rand < 94) return 'TRIGGER_QUICK_FIX';
  if (rand < 97) return 'APPROVE_LIMBO_EXCEPTION';
  return 'GLOBAL_RESET';
}

function generateRandomValue() {
  const type = Math.random();
  if (type < 0.1) return 0;
  if (type < 0.2) return parseFloat((Math.random() * 1000).toFixed(2));
  if (type < 0.7) return parseFloat((Math.random() * 250000).toFixed(2));
  if (type < 0.9) return parseFloat((Math.random() * 2000000).toFixed(2));
  return parseFloat((-Math.random() * 50000).toFixed(2));
}

function runVmChaosFuzzer() {
  console.log(`\n======================================================`);
  console.log(`⚡ AVVIO IN-MEMORY VM CHAOS FUZZER (${CONFIG.totalIterations} ITERAZIONI)`);
  console.log(`======================================================\n`);

  const appJsPath = path.resolve(__dirname, '..', 'src_app', 'app.js');
  if (!fs.existsSync(appJsPath)) {
    throw new Error(`File app.js non trovato in: ${appJsPath}`);
  }
  const appJsCode = fs.readFileSync(appJsPath, 'utf8');

  const { windowMock, documentMock } = createMockDomEnvironment();
  const context = vm.createContext(windowMock);

  // Inietta l'infrastruttura di base e carica app.js
  try {
    vm.runInContext(appJsCode, context, { filename: 'app.js' });
    console.log(`✅ 'app.js' caricato ed inizializzato con successo nel contesto VM.`);
  } catch (initErr) {
    console.error(`❌ Errore critico nel parsing/caricamento di app.js:`, initErr);
    return {
      passed: false,
      error: initErr.message,
      stack: initErr.stack
    };
  }

  const ringBuffer = new RingBuffer(CONFIG.ringBufferCap);
  const detectedTraumas = [];
  let successfulActions = 0;
  let invariantViolationsCount = 0;

  const state = context.state;
  if (!state) {
    throw new Error(`Oggetto 'state' non esposto globalmente da app.js!`);
  }

  // 1. VERIFICA ZERO STATE
  const initialCheck = evaluateInvariants(state);
  console.log(`🔍 Verifica Iniziale Invarianti (Zero State): ${initialCheck.passed ? 'PASSED 🟢' : 'FAILED 🔴'}`);
  if (!initialCheck.passed) {
    detectedTraumas.push({
      type: 'INITIAL_ZERO_STATE_VIOLATION',
      violations: initialCheck.violations
    });
  }

  const CE_KEYS = [
    'ricaviVendite', 'altriRicavi', 'costiMaterieHosting', 'costiServiziMarketing',
    'costiGodimentoBeni', 'salariStipendi', 'oneriSociali', 'tfrQuota',
    'ammImmateriali', 'ammMateriali', 'svalutazioneCrediti', 'oneriDiversi',
    'proventiFinanziari', 'oneriFinanziari', 'imposteIres', 'imposteIrap'
  ];

  const SP_KEYS = [
    'immaterialiLorde', 'materialiLorde', 'finanziarieDepositi',
    'creditiClienti', 'creditiTributari', 'cassa',
    'riservaLegale', 'riserveUtili', 'fondiRischi', 'tfrFondo',
    'debBanche', 'debFornitori', 'debTrib', 'debPrev'
  ];

  // 2. CICLO DI 1.000 ITERAZIONI CHAOS FUZZING
  for (let step = 1; step <= CONFIG.totalIterations; step++) {
    const actionType = pickWeightedAction();
    let actionDetails = { step, action: actionType };

    try {
      if (actionType === 'EDIT_CE_CELL') {
        const key = CE_KEYS[Math.floor(Math.random() * CE_KEYS.length)];
        const yearIdx = Math.floor(Math.random() * 5);
        const newVal = generateRandomValue();
        actionDetails = { ...actionDetails, key, yearIdx, newVal };

        if (!state.fullData.ce[key]) state.fullData.ce[key] = [0, 0, 0, 0, 0];
        state.fullData.ce[key][yearIdx] = newVal;
        if (typeof context.recalculateFinancials === 'function') context.recalculateFinancials();

      } else if (actionType === 'EDIT_SP_CELL') {
        const key = SP_KEYS[Math.floor(Math.random() * SP_KEYS.length)];
        const yearIdx = Math.floor(Math.random() * 5);
        const newVal = Math.abs(generateRandomValue());
        actionDetails = { ...actionDetails, key, yearIdx, newVal };

        if (!state.fullData.sp[key]) state.fullData.sp[key] = [0, 0, 0, 0, 0];
        state.fullData.sp[key][yearIdx] = newVal;
        if (typeof context.recalculateFinancials === 'function') context.recalculateFinancials();

      } else if (actionType === 'ADD_SUBITEM') {
        const parentKey = CE_KEYS[Math.floor(Math.random() * 6)];
        const yearOffset = Math.floor(Math.random() * 5) - 2;
        const amount = generateRandomValue();
        actionDetails = { ...actionDetails, parentKey, yearOffset, amount };

        if (!state.detailedSubitems) state.detailedSubitems = [];
        state.detailedSubitems.push({
          id: `sub_${Date.now()}_${step}`,
          parentKey,
          description: `SubItem #${step}`,
          amount,
          yearOffset,
          type: 'cost'
        });
        if (typeof context.recalculateFinancials === 'function') context.recalculateFinancials();

      } else if (actionType === 'CHANGE_PIVOT_YEAR') {
        const newY0 = 2022 + Math.floor(Math.random() * 6);
        actionDetails = { ...actionDetails, newY0 };
        state.y0 = newY0;
        if (typeof context.recalculateFinancials === 'function') context.recalculateFinancials();

      } else if (actionType === 'TRIGGER_QUICK_FIX') {
        actionDetails = { ...actionDetails, trigger: 'quickFix' };
        if (typeof context.triggerSpQuickFix === 'function') {
          context.triggerSpQuickFix();
        }

      } else if (actionType === 'APPROVE_LIMBO_EXCEPTION') {
        actionDetails = { ...actionDetails, trigger: 'approveAllExceptions' };
        if (typeof context.approveAllExceptions === 'function') {
          context.approveAllExceptions();
        }

      } else if (actionType === 'GLOBAL_RESET') {
        actionDetails = { ...actionDetails, trigger: 'globalResetSession' };
        if (typeof context.globalResetSession === 'function') {
          context.globalResetSession(true);
        }
      }

      // Valutazione Invarianti immediata
      const check = evaluateInvariants(state);
      actionDetails.invariantsPassed = check.passed;
      actionDetails.violations = check.violations;

      if (!check.passed) {
        invariantViolationsCount++;
        detectedTraumas.push({
          type: 'INVARIANT_VIOLATION',
          step,
          action: actionDetails,
          violations: check.violations
        });
      }

      ringBuffer.push(actionDetails);
      successfulActions++;

      if (step % CONFIG.batchSize === 0) {
        console.log(`📊 Progresso: ${step}/${CONFIG.totalIterations} iterazioni completate | Violazioni Invarianti: ${invariantViolationsCount}`);
      }

    } catch (stepErr) {
      detectedTraumas.push({
        type: 'STEP_EXECUTION_ERROR',
        step,
        action: actionDetails,
        error: stepErr.message,
        stack: stepErr.stack
      });
    }
  }

  console.log(`\n🏁 IN-MEMORY VM CHAOS FUZZER COMPLETATO!`);
  console.log(`- Totale azioni eseguite con successo: ${successfulActions}/${CONFIG.totalIterations}`);
  console.log(`- Violazioni Invarianti rilevate: ${invariantViolationsCount}`);
  console.log(`- Traumi / Anomalie Totali registrati: ${detectedTraumas.length}`);

  // Costruzione e Scrittura Atomica del Diagnostic Report
  const diagnosticReport = {
    timestamp: new Date().toISOString(),
    engine: 'In-Memory VM Invariant Fuzzer v1.0',
    totalIterations: CONFIG.totalIterations,
    successfulActions,
    invariantViolationsCount,
    traumasCount: detectedTraumas.length,
    recentTraceBuffer: ringBuffer.toArray(),
    detectedTraumas,
    verdict: detectedTraumas.length === 0 ? 'HEALTHY_GOLDEN_STATE 🟢' : 'TRAUMAS_IDENTIFIED ⚠️'
  };

  const reportDir = path.dirname(CONFIG.reportPath);
  if (!fs.existsSync(reportDir)) {
    fs.mkdirSync(reportDir, { recursive: true });
  }

  // Scrittura atomica
  const tmpReportPath = path.join(os.tmpdir(), `diag_rep_${Date.now()}.json`);
  fs.writeFileSync(tmpReportPath, JSON.stringify(diagnosticReport, null, 2), 'utf8');
  fs.copyFileSync(tmpReportPath, CONFIG.reportPath);
  try { fs.unlinkSync(tmpReportPath); } catch (_) {}

  console.log(`\n📄 Report Diagnostico salvato con successo in: ${CONFIG.reportPath}\n`);
  return diagnosticReport;
}

if (require.main === module) {
  const rep = runVmChaosFuzzer();
  process.exit(0);
}

module.exports = { runVmChaosFuzzer };
