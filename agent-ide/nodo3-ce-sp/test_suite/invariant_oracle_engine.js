/**
 * invariant_oracle_engine.js
 * Oracolo Deterministico di Validazione Invarianti Contabili (Nodo 3: CE & SP Engine)
 * 
 * Regole Invarianti:
 * - INV-01: Quadratura SP (Totale Attivo = Patrimonio Netto + Totale Passivo) entro tolleranza 0.01€
 * - INV-02: Conservazione Somma Sub-voci (Voce Madre = Somma Sub-voci collegate)
 * - INV-03: Idempotenza & Clean Slate Reset (Tutti i parametri azzerati, 0 subitems, 0 eccezioni)
 * - INV-04: Robustezza Numerica (Nessun NaN, null, undefined, Infinity nei calcoli o nel DOM)
 */

function evaluateInvariants(state, domSnapshot = null) {
  const violations = [];
  const tolerance = 0.01;

  if (!state || !state.fullData) {
    violations.push({
      code: 'INV-STATE-CORRUPTED',
      severity: 'CRITICAL',
      message: 'Lo stato globale o state.fullData è nullo o indefinito.'
    });
    return { passed: false, violations };
  }

  const { ce, sp } = state.fullData;
  const numYears = (ce && ce.ricaviVendite && ce.ricaviVendite.length) || 5;

  // Helper per somma array di pari lunghezza
  const sumArrays = (...arrays) => {
    const result = new Array(numYears).fill(0);
    arrays.forEach(arr => {
      if (Array.isArray(arr)) {
        for (let i = 0; i < numYears; i++) {
          const val = Number(arr[i]) || 0;
          result[i] += val;
        }
      }
    });
    return result;
  };

  // 1. VERIFICA INV-04: Assenza di NaN / Infinity / Null nei parametri primari
  const checkNumericIntegrity = (sectionName, sectionObj) => {
    if (!sectionObj) return;
    for (const [key, val] of Object.entries(sectionObj)) {
      if (Array.isArray(val)) {
        val.forEach((item, yearIdx) => {
          if (typeof item === 'number' && (isNaN(item) || !isFinite(item))) {
            violations.push({
              code: 'INV-04-NAN-DETECTED',
              severity: 'CRITICAL',
              message: `Valore non numerico o infinito rilevato in state.${sectionName}.${key}[${yearIdx}]: ${item}`
            });
          }
        });
      } else if (typeof val === 'number' && (isNaN(val) || !isFinite(val))) {
        violations.push({
          code: 'INV-04-NAN-DETECTED',
          severity: 'CRITICAL',
          message: `Valore non numerico o infinito rilevato in state.${sectionName}.${key}: ${val}`
        });
      }
    }
  };

  checkNumericIntegrity('ce', ce);
  checkNumericIntegrity('sp', sp);

  // 2. VERIFICA INV-01: Quadratura Stato Patrimoniale
  // Calcolo Totale Attivo
  const totImmob = sumArrays(sp.immaterialiLorde, sp.materialiLorde, sp.finanziarieDepositi);
  const totAttivoCircolante = sumArrays(sp.creditiClienti, sp.creditiTributari, sp.cassa);
  const totAttivo = sumArrays(totImmob, totAttivoCircolante);

  // Calcolo Totale Passivo & Debiti
  const totDebiti = sumArrays(sp.debBanche, sp.debFornitori, sp.debTrib, sp.debPrev);
  const totFondi = sumArrays(sp.fondiRischi, sp.tfrFondo);
  const totPassivo = sumArrays(totDebiti, totFondi);

  // Calcolo Utile / Perdita d'Esercizio da Conto Economico
  const valoreProduzione = sumArrays(ce.ricaviVendite, ce.altriRicavi);
  const costiProduzione = sumArrays(
    ce.costiMaterieHosting,
    ce.costiServiziMarketing,
    ce.costiGodimentoBeni,
    ce.salariStipendi,
    ce.oneriSociali,
    ce.tfrQuota,
    ce.ammImmateriali,
    ce.ammMateriali,
    ce.svalutazioneCrediti,
    ce.oneriDiversi
  );
  
  const diffValoreCosti = new Array(numYears).fill(0);
  for (let i = 0; i < numYears; i++) diffValoreCosti[i] = valoreProduzione[i] - costiProduzione[i];

  const proventiFin = ce.proventiFinanziari || new Array(numYears).fill(0);
  const oneriFin = ce.oneriFinanziari || new Array(numYears).fill(0);
  const risPrimaImposte = new Array(numYears).fill(0);
  for (let i = 0; i < numYears; i++) risPrimaImposte[i] = diffValoreCosti[i] + (Number(proventiFin[i]) || 0) - (Number(oneriFin[i]) || 0);

  const imposteIres = ce.imposteIres || new Array(numYears).fill(0);
  const imposteIrap = ce.imposteIrap || new Array(numYears).fill(0);
  const utileEsercizio = new Array(numYears).fill(0);
  for (let i = 0; i < numYears; i++) utileEsercizio[i] = risPrimaImposte[i] - ((Number(imposteIres[i]) || 0) + (Number(imposteIrap[i]) || 0));

  // Patrimonio Netto
  const capitaleSociale = Number(sp.capitaleSociale) || 0;
  const riservaLegale = sp.riservaLegale || new Array(numYears).fill(0);
  const riserveUtili = sp.riserveUtili || new Array(numYears).fill(0);

  const patrimonioNetto = new Array(numYears).fill(0);
  const sbilancioSP = new Array(numYears).fill(0);

  for (let y = 0; y < numYears; y++) {
    patrimonioNetto[y] = capitaleSociale + (Number(riservaLegale[y]) || 0) + (Number(riserveUtili[y]) || 0) + utileEsercizio[y];
    const totPassivoNetto = patrimonioNetto[y] + totPassivo[y];
    const diff = Math.abs(totAttivo[y] - totPassivoNetto);
    sbilancioSP[y] = diff;

    if (diff > tolerance) {
      violations.push({
        code: 'INV-01-SP-UNBALANCED',
        severity: 'HIGH',
        yearIndex: y,
        attivo: totAttivo[y],
        passivoENetto: totPassivoNetto,
        delta: diff,
        message: `Sbilancio Stato Patrimoniale all'anno indice ${y}: Attivo=${totAttivo[y].toFixed(2)}€, Passivo+Netto=${totPassivoNetto.toFixed(2)}€ (Delta=${diff.toFixed(2)}€)`
      });
    }
  }

  // 3. VERIFICA INV-02: Conservazione Somma Sub-voci
  if (state.detailedSubitems && Array.isArray(state.detailedSubitems) && state.detailedSubitems.length > 0) {
    // Raggruppa subitems per voce madre e anno
    const subTotals = {};
    state.detailedSubitems.forEach(sub => {
      const key = `${sub.parentKey}_${sub.yearOffset || 0}`;
      subTotals[key] = (subTotals[key] || 0) + (Number(sub.amount) || 0);
    });

    for (const [groupKey, expectedSum] of Object.entries(subTotals)) {
      const [parentKey, yearOffsetStr] = groupKey.split('_');
      const yOffset = parseInt(yearOffsetStr, 10);
      const yIndex = (yOffset >= -2 && yOffset <= 2) ? yOffset + 2 : 2; // offset standard 5 anni (-2 a +2)

      let parentVal = 0;
      if (ce && ce[parentKey] && ce[parentKey][yIndex] !== undefined) {
        parentVal = Number(ce[parentKey][yIndex]) || 0;
      } else if (sp && sp[parentKey] && sp[parentKey][yIndex] !== undefined) {
        parentVal = Number(sp[parentKey][yIndex]) || 0;
      }

      // Se ci sono subitems registrati, la voce madre non può essere disallineata dalla somma se alimentata da breakdown
      if (Math.abs(parentVal - expectedSum) > tolerance && parentVal > 0 && expectedSum > 0) {
        // Warning: possibile incoerenza se la voce madre è stata sovrascritta manualmente senza aggiornare i subitems
        violations.push({
          code: 'INV-02-SUBITEM-MISMATCH',
          severity: 'MEDIUM',
          parentKey,
          yearIndex: yIndex,
          parentVal,
          subSum: expectedSum,
          delta: Math.abs(parentVal - expectedSum),
          message: `Discrepanza tra voce madre '${parentKey}' (${parentVal.toFixed(2)}€) e somma sub-voci (${expectedSum.toFixed(2)}€)`
        });
      }
    }
  }

  // 4. VERIFICA INV-03: Idempotenza Reset (Se applicabile)
  if (state.isDocumentLoaded === false && state.uploadedFiles && state.uploadedFiles.length === 0) {
    // Verifichiamo se ci sono residui fantasma (Ghost Data)
    const hasDetailedSubitems = state.detailedSubitems && state.detailedSubitems.length > 0;
    const hasExceptions = state.exceptionsQueue && state.exceptionsQueue.length > 0;

    if (hasDetailedSubitems) {
      violations.push({
        code: 'INV-03-RESET-GHOST-SUBITEMS',
        severity: 'HIGH',
        subitemsCount: state.detailedSubitems.length,
        message: `Leak di dati post-reset: state.detailedSubitems contiene ancora ${state.detailedSubitems.length} elementi!`
      });
    }
    if (hasExceptions) {
      violations.push({
        code: 'INV-03-RESET-GHOST-EXCEPTIONS',
        severity: 'HIGH',
        exceptionsCount: state.exceptionsQueue.length,
        message: `Leak di dati post-reset: state.exceptionsQueue contiene ancora ${state.exceptionsQueue.length} eccezioni!`
      });
    }
  }

  // 5. VERIFICA DOM SNAPSHOT (Se fornito)
  if (domSnapshot) {
    if (domSnapshot.hasNaNInCells) {
      violations.push({
        code: 'INV-04-DOM-NAN',
        severity: 'CRITICAL',
        message: 'Rilevato testo "NaN" o "undefined" visibile nelle celle della tabella DOM!'
      });
    }
    if (domSnapshot.hasUnbalancedBannerVisible && violations.filter(v => v.code === 'INV-01-SP-UNBALANCED').length === 0) {
      violations.push({
        code: 'INV-01-DOM-FALSE-BANNER',
        severity: 'MEDIUM',
        message: 'Il banner di sbilancio DOM è mostrato ma lo stato matematico risulta in perfetto pareggio.'
      });
    }
  }

  return {
    passed: violations.filter(v => v.severity === 'CRITICAL' || v.severity === 'HIGH').length === 0,
    hasWarningsOnly: violations.length > 0 && violations.every(v => v.severity === 'MEDIUM' || v.severity === 'LOW'),
    violations,
    metrics: {
      numYears,
      totAttivo,
      totPassivo,
      patrimonioNetto,
      sbilancioSP,
      utileEsercizio
    }
  };
}

// Esporta sia per CommonJS / Node.js che per ES6 / Browser
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { evaluateInvariants };
} else if (typeof window !== 'undefined') {
  window.evaluateInvariants = evaluateInvariants;
}
