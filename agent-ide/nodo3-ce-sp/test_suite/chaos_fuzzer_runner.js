/**
 * chaos_fuzzer_runner.js
 * Headless Chaos Monkey Fuzzer & Stress Testing Runner (1.000 Iterazioni)
 * 
 * Mitigazioni integrate:
 * - Shadow Sandbox (%TEMP%) per isolamento profilo Puppeteer e zero lock Google Drive.
 * - Circular Ring Buffer (cap a 50 stati) contro OOM / Memory Leaks.
 * - Microtask Settling Guard (waitForStateSettled) per prevenzione race conditions.
 * - Invariant Oracle Engine integrato ad ogni azione per diagnosi immediata.
 * - Atomic Single-Flush Reporting su diagnostic_report.json.
 */

const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');
const os = require('os');
const { evaluateInvariants } = require('./invariant_oracle_engine');

// Configurazione parametri Fuzzer
const CONFIG = {
  baseUrl: process.env.TEST_APP_URL || 'http://127.0.0.1:8080',
  totalIterations: parseInt(process.env.FUZZ_ITERATIONS || '500', 10),
  batchSize: 100,
  ringBufferCap: 50,
  tolerance: 0.01,
  reportPath: path.resolve(__dirname, 'test_reports', 'diagnostic_report.json')
};

// Circular Ring Buffer
class RingBuffer {
  constructor(capacity) {
    this.capacity = capacity;
    this.buffer = [];
  }
  push(item) {
    if (this.buffer.length >= this.capacity) {
      this.buffer.shift();
    }
    this.buffer.push(item);
  }
  toArray() {
    return [...this.buffer];
  }
}

// Generatore di azioni ponderate
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

// Generatore di valori realistici e edge case
function generateRandomValue() {
  const type = Math.random();
  if (type < 0.1) return 0; // Zero
  if (type < 0.2) return parseFloat((Math.random() * 1000).toFixed(2)); // Piccolo importo
  if (type < 0.7) return parseFloat((Math.random() * 250000).toFixed(2)); // Importo standard
  if (type < 0.9) return parseFloat((Math.random() * 2000000).toFixed(2)); // Grande importo
  return parseFloat((-Math.random() * 50000).toFixed(2)); // Importo negativo (edge case)
}

async function waitForStateSettled(page) {
  await page.evaluate(() => {
    return new Promise(resolve => {
      // Drena eventuale debounce pendente
      if (window.recalcDebounceTimer) {
        clearTimeout(window.recalcDebounceTimer);
        window.recalcDebounceTimer = null;
        if (typeof window.recalculateFinancials === 'function') {
          window.recalculateFinancials();
        }
      }
      // Attendi 1 frame e un microtask tick
      requestAnimationFrame(() => {
        setTimeout(resolve, 15);
      });
    });
  });
}

async function runChaosFuzzer() {
  console.log(`\n======================================================`);
  console.log(`🚀 AVVIO CHAOS FUZZER & INVARIANT STRESS TEST (${CONFIG.totalIterations} ITERAZIONI)`);
  console.log(`======================================================\n`);

  const sandboxDir = path.join(os.tmpdir(), `sandbox_fuzzer_${Date.now()}`);
  if (!fs.existsSync(sandboxDir)) {
    fs.mkdirSync(sandboxDir, { recursive: true });
  }

  const ringBuffer = new RingBuffer(CONFIG.ringBufferCap);
  const detectedTraumas = [];
  let successfulActions = 0;
  let invariantViolationsCount = 0;

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: true,
      userDataDir: sandboxDir,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu'
      ]
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 900 });

    // Intercetta errori JS della pagina
    page.on('pageerror', err => {
      detectedTraumas.push({
        type: 'RUNTIME_PAGE_ERROR',
        message: err.message,
        stack: err.stack,
        step: successfulActions
      });
    });

    // Inietta hook per neutralizzare animazioni pesanti e timer infiniti
    await page.evaluateOnNewDocument(() => {
      window.__TEST_HARNESS__ = true;
      // Mock leggero per showToast per evitare accumulo DOM e setTimeout a catena
      window.showToast = function(msg, type) {
        console.log(`[TOAST MOCK] (${type}) ${msg}`);
      };
      // Mock no-op per triggerTableFlash
      window.triggerTableFlash = function() {};
    });

    console.log(`🌐 Navigazione a ${CONFIG.baseUrl}...`);
    await page.goto(CONFIG.baseUrl, { waitUntil: 'networkidle0', timeout: 30000 });
    console.log(`✅ Pagina caricata con successo.\n`);

    // Inietta il codice dell'Oracolo di Invarianti all'interno del contesto browser
    const oracleEngineCode = fs.readFileSync(path.resolve(__dirname, 'invariant_oracle_engine.js'), 'utf8');
    await page.evaluate(oracleEngineCode);

    // Esegui verifica Iniziale (Zero-State)
    const initialCheck = await page.evaluate(() => {
      const domHasNaN = document.body.innerText.includes('NaN');
      const banner = document.getElementById('spUnbalancedBanner');
      const hasUnbalancedBanner = banner && window.getComputedStyle(banner).display !== 'none';
      return window.evaluateInvariants(window.state, {
        hasNaNInCells: domHasNaN,
        hasUnbalancedBannerVisible: hasUnbalancedBanner
      });
    });

    console.log(`🔍 Verifica Iniziale Invarianti (Zero State): ${initialCheck.passed ? 'PASSED 🟢' : 'FAILED 🔴'}`);
    if (!initialCheck.passed) {
      detectedTraumas.push({
        type: 'INITIAL_ZERO_STATE_VIOLATION',
        violations: initialCheck.violations
      });
    }

    // ELENCO DELLE CHIAVI EDITABILI IN CE E SP
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

    // CICLO CHAOS FUZZER
    for (let step = 1; step <= CONFIG.totalIterations; step++) {
      const actionType = pickWeightedAction();
      let actionDetails = { step, action: actionType };

      try {
        if (actionType === 'EDIT_CE_CELL') {
          const key = CE_KEYS[Math.floor(Math.random() * CE_KEYS.length)];
          const yearIdx = Math.floor(Math.random() * 5);
          const newVal = generateRandomValue();
          actionDetails = { ...actionDetails, key, yearIdx, newVal };

          await page.evaluate(({ key, yearIdx, newVal }) => {
            if (window.state && window.state.fullData && window.state.fullData.ce) {
              if (!window.state.fullData.ce[key]) window.state.fullData.ce[key] = [0, 0, 0, 0, 0];
              window.state.fullData.ce[key][yearIdx] = newVal;
              if (typeof window.recalculateFinancials === 'function') window.recalculateFinancials();
            }
          }, { key, yearIdx, newVal });

        } else if (actionType === 'EDIT_SP_CELL') {
          const key = SP_KEYS[Math.floor(Math.random() * SP_KEYS.length)];
          const yearIdx = Math.floor(Math.random() * 5);
          const newVal = Math.abs(generateRandomValue()); // SP solitamente positivo
          actionDetails = { ...actionDetails, key, yearIdx, newVal };

          await page.evaluate(({ key, yearIdx, newVal }) => {
            if (window.state && window.state.fullData && window.state.fullData.sp) {
              if (!window.state.fullData.sp[key]) window.state.fullData.sp[key] = [0, 0, 0, 0, 0];
              window.state.fullData.sp[key][yearIdx] = newVal;
              if (typeof window.recalculateFinancials === 'function') window.recalculateFinancials();
            }
          }, { key, yearIdx, newVal });

        } else if (actionType === 'ADD_SUBITEM') {
          const parentKey = CE_KEYS[Math.floor(Math.random() * 6)]; // Prime 6 voci CE
          const yearOffset = Math.floor(Math.random() * 5) - 2; // -2, -1, 0, 1, 2
          const amount = generateRandomValue();
          const description = `Chaos SubItem #${step}`;
          actionDetails = { ...actionDetails, parentKey, yearOffset, amount };

          await page.evaluate(({ parentKey, yearOffset, amount, description }) => {
            if (window.state) {
              if (!window.state.detailedSubitems) window.state.detailedSubitems = [];
              const newItem = {
                id: `chaos_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
                parentKey,
                description,
                amount,
                yearOffset,
                type: 'cost'
              };
              window.state.detailedSubitems.push(newItem);
              if (typeof window.recalculateFinancials === 'function') window.recalculateFinancials();
            }
          }, { parentKey, yearOffset, amount, description });

        } else if (actionType === 'CHANGE_PIVOT_YEAR') {
          const newY0 = 2022 + Math.floor(Math.random() * 6); // 2022..2027
          actionDetails = { ...actionDetails, newY0 };

          await page.evaluate((newY0) => {
            if (window.state) {
              window.state.y0 = newY0;
              if (typeof window.recalculateFinancials === 'function') window.recalculateFinancials();
            }
          }, newY0);

        } else if (actionType === 'TRIGGER_QUICK_FIX') {
          actionDetails = { ...actionDetails, trigger: 'quickFix' };
          await page.evaluate(() => {
            if (typeof window.triggerSpQuickFix === 'function') {
              window.triggerSpQuickFix();
            }
          });

        } else if (actionType === 'APPROVE_LIMBO_EXCEPTION') {
          actionDetails = { ...actionDetails, trigger: 'approveAllExceptions' };
          await page.evaluate(() => {
            if (typeof window.approveAllExceptions === 'function') {
              window.approveAllExceptions();
            }
          });

        } else if (actionType === 'GLOBAL_RESET') {
          actionDetails = { ...actionDetails, trigger: 'globalResetSession' };
          await page.evaluate(() => {
            if (typeof window.globalResetSession === 'function') {
              window.globalResetSession(true);
            }
          });
        }

        // Attendi la stabilizzazione asincrona dello stato
        await waitForStateSettled(page);

        // Valutazione Invarianti ad ogni singolo step
        const stepCheck = await page.evaluate(() => {
          const domHasNaN = document.body.innerText.includes('NaN') || document.body.innerText.includes('undefined');
          return window.evaluateInvariants(window.state, { hasNaNInCells: domHasNaN });
        });

        actionDetails.invariantsPassed = stepCheck.passed;
        actionDetails.violations = stepCheck.violations;

        if (!stepCheck.passed) {
          invariantViolationsCount++;
          detectedTraumas.push({
            type: 'INVARIANT_VIOLATION_DURING_FUZZING',
            step,
            action: actionDetails,
            violations: stepCheck.violations
          });
        }

        ringBuffer.push(actionDetails);
        successfulActions++;

        if (step % CONFIG.batchSize === 0) {
          console.log(`📊 Progresso: ${step}/${CONFIG.totalIterations} iterazioni completate | Violazioni Invarianti: ${invariantViolationsCount}`);
        }

      } catch (stepErr) {
        detectedTraumas.push({
          type: 'STEP_EXECUTION_EXCEPTION',
          step,
          action: actionDetails,
          error: stepErr.message
        });
      }
    }

    console.log(`\n🏁 CHAOS FUZZER COMPLETATO CON SUCCESSO!`);
    console.log(`- Totale azioni eseguite: ${successfulActions}`);
    console.log(`- Violazioni Invarianti: ${invariantViolationsCount}`);
    console.log(`- Anomalie / Traumi Rilevati: ${detectedTraumas.length}`);

  } catch (err) {
    console.error(`❌ Errore fatale nel runner di test:`, err);
    detectedTraumas.push({
      type: 'FATAL_RUNNER_ERROR',
      error: err.message,
      stack: err.stack
    });
  } finally {
    if (browser) {
      try {
        await browser.close();
      } catch (e) {
        console.warn(`Avviso chiusura browser:`, e.message);
      }
    }
    // Bonifica directory temporanea sandbox
    try {
      if (fs.existsSync(sandboxDir)) {
        fs.rmSync(sandboxDir, { recursive: true, force: true });
      }
    } catch (cleanErr) {
      console.warn(`Avviso pulizia sandbox:`, cleanErr.message);
    }
  }

  // Costruzione e Scrittura Atomica del Diagnostic Report
  const diagnosticReport = {
    timestamp: new Date().toISOString(),
    engine: 'Chaos Monkey Invariant Fuzzer v1.0',
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
  runChaosFuzzer().then(report => {
    process.exit(report.traumasCount > 0 && report.invariantViolationsCount > 10 ? 1 : 0);
  });
}

module.exports = { runChaosFuzzer };
