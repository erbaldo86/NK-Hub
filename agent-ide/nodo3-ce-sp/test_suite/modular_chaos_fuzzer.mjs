/**
 * modular_chaos_fuzzer.mjs
 * 1,000 Iterations Chaos Fuzzer on ES6 Modular Architecture
 * 
 * Stresses State, Financial Engine, Subitems Aggregator, and QuickFix.
 */

import * as State from '../src_app/modules/state.js';
import * as FinancialEngine from '../src_app/modules/financial_engine.js';
import { CE_KEYS, SP_KEYS } from '../src_app/modules/constants.js';

const TOTAL_ITERATIONS = 1000;

function generateRandomValue() {
  const type = Math.random();
  if (type < 0.1) return 0;
  if (type < 0.2) return parseFloat((Math.random() * 1000).toFixed(2));
  if (type < 0.7) return parseFloat((Math.random() * 250000).toFixed(2));
  if (type < 0.9) return parseFloat((Math.random() * 2000000).toFixed(2));
  return parseFloat((-Math.random() * 50000).toFixed(2));
}

export function runModularChaosFuzzer() {
  console.log(`\n======================================================`);
  console.log(`⚡ AVVIO MODULAR CHAOS FUZZER (${TOTAL_ITERATIONS} ITERAZIONI)`);
  console.log(`======================================================\n`);

  State.resetState();
  let errors = 0;
  let successfulActions = 0;

  for (let i = 1; i <= TOTAL_ITERATIONS; i++) {
    const actionType = Math.random();

    try {
      if (actionType < 0.35) {
        // Edit CE Cell
        const key = CE_KEYS[Math.floor(Math.random() * CE_KEYS.length)];
        const timeline = State.getTimelineYears();
        const yearObj = timeline[Math.floor(Math.random() * timeline.length)];
        const rec = State.ensureYearRecord(yearObj.year);
        rec.ce[key] = generateRandomValue();
        FinancialEngine.recalculateFinancials();
        successfulActions++;
      } else if (actionType < 0.65) {
        // Edit SP Cell
        const key = SP_KEYS[Math.floor(Math.random() * SP_KEYS.length)];
        const timeline = State.getTimelineYears();
        const yearObj = timeline[Math.floor(Math.random() * timeline.length)];
        const rec = State.ensureYearRecord(yearObj.year);
        rec.sp[key] = generateRandomValue();
        FinancialEngine.recalculateFinancials();
        successfulActions++;
      } else if (actionType < 0.78) {
        // Add Subitem
        const subSec = ['costiServiziMarketing', 'costiMaterieHosting', 'salariStipendi'][Math.floor(Math.random() * 3)];
        const timeline = State.getTimelineYears();
        const yearObj = timeline[Math.floor(Math.random() * timeline.length)];
        const st = State.getState();
        st.detailedSubitems.push({
          id: `sub_${Date.now()}_${Math.random()}`,
          name: `Voce Chaos ${i}`,
          category: 'Spesa Generale',
          section: subSec,
          year: yearObj.year,
          value: Math.round(Math.random() * 25000)
        });
        FinancialEngine.recalculateFinancials();
        successfulActions++;
      } else if (actionType < 0.88) {
        // Change Pivot Year
        const newPivot = 2020 + Math.floor(Math.random() * 10);
        State.setPivotYear(newPivot);
        FinancialEngine.recalculateFinancials();
        successfulActions++;
      } else if (actionType < 0.96) {
        // Quick Fix SP Balance
        FinancialEngine.balanceSPQuickFix();
        successfulActions++;
      } else {
        // Reset State
        State.resetState();
        FinancialEngine.recalculateFinancials();
        successfulActions++;
      }

      // Check numeric integrity on calculated years
      const currentYears = State.getState().years;
      for (const yr of currentYears) {
        for (const [k, val] of Object.entries(yr)) {
          if (typeof val === 'number' && (isNaN(val) || !isFinite(val))) {
            throw new Error(`NaN/Infinite detected in years[${yr.year}].${k}: ${val}`);
          }
        }
      }

    } catch (err) {
      errors++;
      console.error(`❌ Errore alla iterazione #${i}:`, err.message);
    }
  }

  console.log(`\n📊 REPORT MODULAR CHAOS FUZZER:`);
  console.log(`   - Iterazioni totali: ${TOTAL_ITERATIONS}`);
  console.log(`   - Azioni riuscite: ${successfulActions}`);
  console.log(`   - Errori / Crash: ${errors}`);

  if (errors === 0) {
    console.log(`\n🏆 RESILIENZA COMPLETA CONFERMATA: 0 crash su 1.000 iterazioni! 🟢\n`);
    return true;
  } else {
    console.log(`\n❌ Fuzzer terminato con ${errors} errori.\n`);
    return false;
  }
}

if (process.argv[1].endsWith('modular_chaos_fuzzer.mjs')) {
  const success = runModularChaosFuzzer();
  process.exit(success ? 0 : 1);
}
