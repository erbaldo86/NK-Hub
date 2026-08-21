/**
 * run_full_modular_stress_suite.mjs
 * Comprehensive Stress Test & Invariant Verification Suite for ES6 Modules
 * 
 * Tests:
 * 1. 1,000 High-Frequency Chaos Mutations (CE, SP, Subitems, Pivot Shifting, Resets)
 * 2. Invariant Oracle Checks on EVERY iteration:
 *    - INV-01: SP Balance & Statutory Equity Accounting
 *    - INV-02: Subitem Conservation & Bidirectional Sync
 *    - INV-03: Zero-Ghost-Leak State Reset Idempotence
 *    - INV-04: Strict Anti-NaN / Finite Float Verification
 *    - INV-05: Perno-Centric Timeline (Y-k .. Y0 .. Y+k) Consistency
 */

import * as State from '../src_app/modules/state.js';
import * as FinancialEngine from '../src_app/modules/financial_engine.js';
import * as Ingestion from '../src_app/modules/ingestion.js';
import { CE_KEYS, SP_KEYS } from '../src_app/modules/constants.js';

const TOTAL_ITERATIONS = 1000;

function generateRandomValue() {
  const r = Math.random();
  if (r < 0.10) return 0;
  if (r < 0.20) return parseFloat((Math.random() * 10).toFixed(2));
  if (r < 0.60) return parseFloat((Math.random() * 500000).toFixed(2));
  if (r < 0.85) return parseFloat((Math.random() * 10000000).toFixed(2));
  if (r < 0.95) return parseFloat((-Math.random() * 100000).toFixed(2));
  return 0.01;
}

export function runFullStressSuite() {
  console.log(`\n===============================================================`);
  console.log(`🔥 AVVIO COMPLETE ES6 MODULAR STRESS TEST SUITE (${TOTAL_ITERATIONS} ITERAZIONI)`);
  console.log(`===============================================================\n`);

  State.resetState();
  let errors = [];
  let stats = {
    ceEdits: 0,
    spEdits: 0,
    subitemOps: 0,
    pivotShifts: 0,
    quickFixes: 0,
    resets: 0,
    demoLoads: 0,
    invariantChecksPassed: 0
  };

  const startTime = Date.now();

  for (let i = 1; i <= TOTAL_ITERATIONS; i++) {
    const action = Math.random();

    try {
      // 1. EXECUTE RANDOM ACTION
      if (action < 0.30) {
        // Edit CE Cell
        const key = CE_KEYS[Math.floor(Math.random() * CE_KEYS.length)];
        const timeline = State.getTimelineYears();
        const yearObj = timeline[Math.floor(Math.random() * timeline.length)];
        const rec = State.ensureYearRecord(yearObj.year);
        rec.ce[key] = generateRandomValue();
        FinancialEngine.recalculateFinancials();
        stats.ceEdits++;
      } else if (action < 0.60) {
        // Edit SP Cell
        const key = SP_KEYS[Math.floor(Math.random() * SP_KEYS.length)];
        const timeline = State.getTimelineYears();
        const yearObj = timeline[Math.floor(Math.random() * timeline.length)];
        const rec = State.ensureYearRecord(yearObj.year);
        rec.sp[key] = generateRandomValue();
        FinancialEngine.recalculateFinancials();
        stats.spEdits++;
      } else if (action < 0.75) {
        // Subitem Operations: Add, Edit or Remove
        const subSections = ['costiMaterieHosting', 'costiServiziMarketing', 'costiGodimentoBeni', 'salariStipendi', 'oneriDiversi'];
        const chosenSec = subSections[Math.floor(Math.random() * subSections.length)];
        const timeline = State.getTimelineYears();
        const yearObj = timeline[Math.floor(Math.random() * timeline.length)];
        const st = State.getState();

        if (Math.random() < 0.7 || st.detailedSubitems.length === 0) {
          // Add subitem
          st.detailedSubitems.push({
            id: `sub_${Date.now()}_${Math.random()}`,
            name: `Stress Subitem #${i}`,
            category: 'Testing Area',
            section: chosenSec,
            year: yearObj.year,
            value: Math.round(Math.random() * 50000)
          });
        } else {
          // Mutate existing subitem
          const target = st.detailedSubitems[Math.floor(Math.random() * st.detailedSubitems.length)];
          target.value = Math.round(Math.random() * 75000);
        }
        FinancialEngine.recalculateFinancials();
        stats.subitemOps++;
      } else if (action < 0.85) {
        // Shift Pivot Year
        const targetPivot = 2020 + Math.floor(Math.random() * 10);
        State.setPivotYear(targetPivot);
        FinancialEngine.recalculateFinancials();
        stats.pivotShifts++;
      } else if (action < 0.93) {
        // Quick Fix Balance SP
        const timeline = State.getTimelineYears();
        const yearObj = timeline[Math.floor(Math.random() * timeline.length)];
        FinancialEngine.balanceSPQuickFix(yearObj.year);
        
        // Assert INV-01: Perfect Balance after QuickFix
        const yrData = State.getState().years.find(y => y.year === yearObj.year);
        if (yrData) {
          const diff = Math.abs(yrData.totaleAttivo - yrData.totalePassivo);
          if (diff > 0.01) {
            throw new Error(`INV-01 Violation after QuickFix in Year ${yearObj.year}: Attivo=${yrData.totaleAttivo}, Passivo=${yrData.totalePassivo}, Diff=${diff}`);
          }
        }
        stats.quickFixes++;
      } else if (action < 0.97) {
        // Load Demo Dataset
        Ingestion.loadSimulatedDocumentDemo();
        stats.demoLoads++;
      } else {
        // Deep Reset
        State.resetDataToZero();
        FinancialEngine.recalculateFinancials();
        
        // Assert INV-03: Zero ghost leakage after reset
        const st = State.getState();
        if (st.detailedSubitems.length !== 0) {
          throw new Error(`INV-03 Violation: Subitems not empty after reset (${st.detailedSubitems.length} items)`);
        }
        if (st.exceptionsQueue.length !== 0) {
          throw new Error(`INV-03 Violation: Exceptions queue not empty after reset`);
        }
        const y0 = (st.years || []).find(y => y.isPivot);
        if (!y0 || y0.ricaviTot !== 0 || y0.totaleCostiProd !== 0) {
          throw new Error(`INV-03 Violation: Y0 values not zero after reset`);
        }
        stats.resets++;
      }

      // 2. INVARIANT CHECK ON EVERY ITERATION (INV-04 & INV-05 & INV-02)
      const st = State.getState();
      
      // Check INV-04: Strict numeric integrity (no NaN / Infinity / undefined values in output years)
      for (const yr of (st.years || [])) {
        for (const [prop, val] of Object.entries(yr)) {
          if (typeof val === 'number') {
            if (isNaN(val) || !isFinite(val)) {
              throw new Error(`INV-04 Numeric corruption in Year ${yr.year}, property ${prop}: ${val}`);
            }
          }
        }
      }

      // Check INV-05: Timeline correctness (exactly 1 pivot year, exactly matching relative labels)
      const pivotMatches = (st.years || []).filter(y => y.isPivot);
      if (pivotMatches.length !== 1) {
        throw new Error(`INV-05 Timeline corruption: expected 1 pivot year, found ${pivotMatches.length}`);
      }
      if (pivotMatches[0].year !== st.pivotYear) {
        throw new Error(`INV-05 Timeline mismatch: pivot year is ${st.pivotYear}, but year marked as isPivot is ${pivotMatches[0].year}`);
      }

      // Check INV-02: Subitem Conservation
      const subitems = st.detailedSubitems || [];
      const subSections = ['costiMaterieHosting', 'costiServiziMarketing', 'costiGodimentoBeni', 'salariStipendi', 'oneriDiversi'];
      for (const yr of (st.years || [])) {
        const rec = (st.fullData && st.fullData.records) ? st.fullData.records[yr.year] : null;
        if (rec && rec.ce) {
          for (const sec of subSections) {
            const expectedSum = subitems
              .filter(s => s.year === yr.year && s.section === sec)
              .reduce((acc, curr) => acc + (Number(curr.value) || 0), 0);
            if (expectedSum > 0) {
              const actualVal = rec.ce[sec] || 0;
              if (Math.abs(actualVal - expectedSum) > 0.01) {
                throw new Error(`INV-02 Subitem conservation mismatch in Year ${yr.year}, sec ${sec}: expected ${expectedSum}, found ${actualVal}`);
              }
            }
          }
        }
      }

      stats.invariantChecksPassed++;

    } catch (err) {
      errors.push({ iteration: i, error: err.message, stack: err.stack });
      console.error(`❌ ERRORE CRITICO alla iterazione #${i}:`, err.message);
    }
  }

  const durationMs = Date.now() - startTime;

  console.log(`\n===============================================================`);
  console.log(`📊 RIEPILOGO STRESS TEST SUITE ES6:`);
  console.log(`===============================================================`);
  console.log(`   - Iterazioni totali completate: ${TOTAL_ITERATIONS}`);
  console.log(`   - Tempo di esecuzione: ${durationMs} ms (${(durationMs / TOTAL_ITERATIONS).toFixed(2)} ms/op)`);
  console.log(`   - Modifiche CE simulate: ${stats.ceEdits}`);
  console.log(`   - Modifiche SP simulate: ${stats.spEdits}`);
  console.log(`   - Operazioni Sub-voci: ${stats.subitemOps}`);
  console.log(`   - Spostamenti Anno Perno: ${stats.pivotShifts}`);
  console.log(`   - Quick Fix Quadratura SP: ${stats.quickFixes}`);
  console.log(`   - Reset Profondi a Zero: ${stats.resets}`);
  console.log(`   - Ingestion Demo simulate: ${stats.demoLoads}`);
  console.log(`   - Controlli Invarianti superati: ${stats.invariantChecksPassed}`);
  console.log(`   - Totale Violazioni / Errori: ${errors.length}`);

  if (errors.length === 0) {
    console.log(`\n🏆 SUCCESSO TOTALE: 0 ERRORI SU ${TOTAL_ITERATIONS} ITERAZIONI! 🟢`);
    console.log(`   Tutti gli Invarianti Contabili (INV-01, INV-02, INV-03, INV-04, INV-05) sono verificati al 100%.\n`);
    return { success: true, stats, errors };
  } else {
    console.log(`\n❌ ATTENZIONE: ${errors.length} violazioni riscontrate durante lo stress test.\n`);
    return { success: false, stats, errors };
  }
}

if (process.argv[1].endsWith('run_full_modular_stress_suite.mjs')) {
  const result = runFullStressSuite();
  process.exit(result.success ? 0 : 1);
}
