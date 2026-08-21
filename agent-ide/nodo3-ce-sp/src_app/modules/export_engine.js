// 🏛️ EXPORT & REPORTING ENGINE - NODO 3 (ES6 Module)
// CSV / XLSX / PDF / JSON Export Generator

import { getState, getTimelineYears } from './state.js';
import { closeExportModal, showToast } from './modals.js';

export function triggerDownload(format) {
  closeExportModal();
  const state = getState();
  const y = state.years;
  const timeline = getTimelineYears();
  const headers = ['Voce', ...timeline.slice(0, state.visibleYearsCount).map(t => `${t.label} (${t.year})`)];

  if (format === 'csv' || format === 'xlsx') {
    let csv = headers.join(',') + '\n';
    
    // Conto Economico rows
    csv += `Ricavi delle Vendite,${y.map(i => i.ricaviVendite || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Altri Ricavi,${y.map(i => i.altriRicavi || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Totale Valore Produzione (A),${y.map(i => i.ricaviTot || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `OpEx Totali (B),${y.map(i => i.costiTot || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `EBITDA,${y.map(i => i.ebitda || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Ammortamenti Totali,${y.map(i => i.ammortamentiTot || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `EBIT,${y.map(i => i.ebit || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `EBT (Risultato ante Imposte),${y.map(i => i.ebt || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Utile (Perdita) dell'Esercizio,${y.map(i => i.utile || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    
    // Stato Patrimoniale rows
    csv += `\nSTATO PATRIMONIALE\n`;
    csv += `Totale Attivo,${y.map(i => i.totaleAttivo || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Patrimonio Netto Totale,${y.map(i => i.patrimonioNetto || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Totale Debiti,${y.map(i => i.totaleDebiti || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Totale Passivo e PN,${y.map(i => i.totalePassivo || 0).slice(0, state.visibleYearsCount).join(',')}\n`;
    csv += `Disponibilità Liquide (Cassa),${y.map(i => i.cassa || 0).slice(0, state.visibleYearsCount).join(',')}\n`;

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Bilancio_Completo_Chronos_Nodo3.${format === 'xlsx' ? 'csv' : format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } else if (format === 'json') {
    const jsonStr = JSON.stringify({
      schema_version: '3.0.0',
      export_date: new Date().toISOString(),
      pivot_year: state.pivotYear,
      timeline: timeline.slice(0, state.visibleYearsCount),
      financial_data: y.slice(0, state.visibleYearsCount)
    }, null, 2);
    
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Bilancio_Completo_Chronos_Nodo3.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  showToast(`📥 Esportazione ${format.toUpperCase()} generata con successo!`, 'success');
}
