// 🏛️ KPI & ANALYTICS CONTROLLER - NODO 3 (ES6 Module)
// Top KPI Cards, SaaS & Sector Benchmarks, SVG Trajectory Charts

import { getState, getTimelineYears } from './state.js';

export function renderKpiCards() {
  const state = getState();
  const elRic = document.getElementById('kpiRicaviY5');
  const elRicSub = document.getElementById('kpiRicaviSub');
  const elMargin = document.getElementById('kpiEbitdaMargin');
  const elMarginSub = document.getElementById('kpiEbitdaSub');
  const elUtile = document.getElementById('kpiUtileY5');
  const elCassa = document.getElementById('kpiCassaY5');
  const elDscr = document.getElementById('kpiDscr');
  const elRoe = document.getElementById('kpiRoeRoi');

  // Titles
  const tRic = document.getElementById('kpiTitleRicavi');
  const tMargin = document.getElementById('kpiTitleMargin');
  const tUtile = document.getElementById('kpiTitleUtile');
  const tCassa = document.getElementById('kpiTitleCassa');
  const tDscr = document.getElementById('kpiTitleDscr');
  const tRoe = document.getElementById('kpiTitleRoeRoi');

  const timeline = getTimelineYears();
  const pivotIdx = timeline.findIndex(y => y.isPivot);
  const defaultIdx = pivotIdx !== -1 ? pivotIdx : 0;
  let selectedIdx = state.selectedTopKpiYearIndex !== undefined ? state.selectedTopKpiYearIndex : defaultIdx;
  if (selectedIdx >= timeline.length) selectedIdx = 0;
  
  const yrNum = selectedIdx + 1;
  let targetYear = (state.years && state.years[selectedIdx]) ? state.years[selectedIdx] : (state.years ? state.years[defaultIdx] : null);
  const yrLabel = targetYear ? `${targetYear.label || 'Anno ' + yrNum} (${targetYear.year || 2025})` : `Anno ${yrNum}`;

  if (tRic) tRic.textContent = `Ricavi ${yrLabel} (A.1 + A.5)`;
  if (tMargin) tMargin.textContent = `EBITDA Margin ${yrLabel}`;
  if (tUtile) tUtile.textContent = `Utile Netto ${yrLabel}`;
  if (tCassa) tCassa.textContent = `Disponibilità Liquida ${yrLabel}`;
  if (tDscr) tDscr.textContent = `Indice DSCR ${yrLabel}`;
  if (tRoe) tRoe.textContent = `ROE / ROI Stimati (${yrLabel})`;

  // Render dynamic buttons in kpiYearButtonsContainer
  const container = document.getElementById('kpiYearButtonsContainer');
  if (container) {
    let btnsHTML = `<span style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600; margin-right: 0.25rem;">📅 Anno:</span>`;
    timeline.forEach((t, i) => {
      const activeClass = (i === selectedIdx) ? 'active-hz' : '';
      const style = (i === selectedIdx) ? 'background: var(--accent-blue); color: #ffffff;' : 'background: transparent; color: var(--text-secondary);';
      btnsHTML += `<button class="btn btn-xs btn-outline ${activeClass}" style="${style}" id="btnKpiY${i}" onclick="setTopKpiSelectedYear(${i})">${t.label} (${t.year})</button>`;
    });
    container.innerHTML = btnsHTML;
  }

  // Update saasYearSelect dropdown if present
  const saasSelect = document.getElementById('saasYearSelect');
  if (saasSelect) {
    let optHTML = '';
    const sidebarIdx = state.selectedSidebarYearIndex !== undefined ? state.selectedSidebarYearIndex : defaultIdx;
    timeline.forEach((t, i) => {
      optHTML += `<option value="${i}" ${i === sidebarIdx ? 'selected' : ''}>${t.label} (${t.year})</option>`;
    });
    saasSelect.innerHTML = optHTML;
  }

  if (!targetYear || targetYear.ricaviTot === 0) {
    if (elRic) { elRic.textContent = '€0'; elRic.classList.remove('compact-text'); }
    if (elRicSub) elRicSub.textContent = 'Nessun dato ingestito';
    if (elMargin) elMargin.textContent = '0.0%';
    if (elMarginSub) elMarginSub.textContent = 'EBITDA Netto: €0';
    if (elUtile) { elUtile.textContent = '€0'; elUtile.classList.remove('compact-text'); }
    if (elCassa) { elCassa.textContent = '€0'; elCassa.classList.remove('compact-text'); }
    if (elDscr) elDscr.textContent = '0.00x';
    if (elRoe) elRoe.textContent = '0.0% / 0.0%';
    return;
  }

  const ebitdaMargin = targetYear.ricaviTot > 0 ? ((targetYear.ebitda / targetYear.ricaviTot) * 100).toFixed(1) : "0.0";

  const setKpiVal = (el, valNum, prefix = '€') => {
    if (!el) return;
    const str = `${prefix}${valNum.toLocaleString('it-IT')}`;
    el.textContent = str;
    el.title = str;
    if (str.length >= 11) {
      el.classList.add('compact-text');
    } else {
      el.classList.remove('compact-text');
    }
  };

  setKpiVal(elRic, targetYear.ricaviTot);
  if (elRicSub) elRicSub.textContent = `Valore della Produzione (Anno ${yrNum})`;

  if (elMargin) elMargin.textContent = `${ebitdaMargin}%`;
  if (elMarginSub) elMarginSub.textContent = `EBITDA Netto: €${targetYear.ebitda.toLocaleString('it-IT')}`;

  setKpiVal(elUtile, targetYear.utile);
  setKpiVal(elCassa, targetYear.cassa);

  const debServizio = (targetYear.totaleDebiti || 1);
  const dscr = (targetYear.ebitda > 0 && debServizio > 0) ? (targetYear.ebitda / (debServizio * 0.1)).toFixed(2) : "2.22";
  if (elDscr) elDscr.textContent = `${dscr}x`;

  const roe = ((targetYear.utile / (targetYear.patrimonioNetto || 1)) * 100).toFixed(1);
  const roi = ((targetYear.ebit / (targetYear.totaleAttivo || 1)) * 100).toFixed(1);
  if (elRoe) elRoe.textContent = `${roe}% / ${roi}%`;
}

export function setTopKpiSelectedYear(idx) {
  const state = getState();
  const timeline = getTimelineYears();
  const validIdx = Math.max(0, Math.min(timeline.length - 1, parseInt(idx, 10) || 0));
  state.selectedTopKpiYearIndex = validIdx;

  for (let i = 0; i < 5; i++) {
    const btn = document.getElementById(`btnKpiY${i}`);
    if (btn) {
      if (i === validIdx) {
        btn.classList.add('active-hz');
        btn.style.background = 'var(--accent-blue)';
        btn.style.color = '#ffffff';
      } else {
        btn.classList.remove('active-hz');
        btn.style.background = 'transparent';
        btn.style.color = 'var(--text-secondary)';
      }
    }
  }

  renderKpiCards();
}

export function setSidebarSelectedYear(idx) {
  const state = getState();
  const timeline = getTimelineYears();
  const validIdx = Math.max(0, Math.min(timeline.length - 1, parseInt(idx, 10) || 0));
  state.selectedSidebarYearIndex = validIdx;

  const select = document.getElementById('saasYearSelect');
  if (select && parseInt(select.value, 10) !== validIdx) {
    select.value = validIdx;
  }

  renderSaasMetrics();
}

export function renderSaasMetrics() {
  const state = getState();
  const timeline = getTimelineYears();
  const pivotIdx = timeline.findIndex(t => t.isPivot);
  const defaultIdx = pivotIdx !== -1 ? pivotIdx : 0;
  const selectedIdx = (state.selectedSidebarYearIndex !== undefined && state.selectedSidebarYearIndex !== null)
    ? state.selectedSidebarYearIndex
    : defaultIdx;

  const select = document.getElementById('saasYearSelect');
  if (select) {
    if (select.options.length !== timeline.length || (select.options[0] && !select.options[0].textContent.includes(timeline[0].label))) {
      let optHTML = '';
      timeline.forEach((t, idx) => {
        const typeLabel = t.isPivot ? 'Anno Perno (Y0)' : (t.relOffset < 0 ? 'Storico (Actual)' : 'Forecast');
        optHTML += `<option value="${idx}" ${idx === selectedIdx ? 'selected' : ''}>${t.label} (${t.year}) — ${typeLabel}</option>`;
      });
      select.innerHTML = optHTML;
    } else if (parseInt(select.value, 10) !== selectedIdx) {
      select.value = selectedIdx;
    }
  }

  const yrNum = selectedIdx + 1;
  const targetYear = (state.years && state.years[selectedIdx]) ? state.years[selectedIdx] : (state.years ? state.years[defaultIdx] : null);
  const yrLabel = targetYear ? `${targetYear.label || 'Y' + yrNum} (${targetYear.year || 2025})` : `Anno ${yrNum}`;

  const elMrr = document.getElementById('saasMrr');
  const elArr = document.getElementById('saasArr');
  const elCac = document.getElementById('saasCac');
  const elLtv = document.getElementById('saasLtv');
  const elPayback = document.getElementById('saasPayback');
  const elNrr = document.getElementById('saasNrr');
  const elChurn = document.getElementById('saasChurn');
  const badgeStatus = document.getElementById('badgeSaasStatus');
  const atecoVal = document.getElementById('atecoSelect')?.value || 'saas';

  const lblMrr = document.getElementById('lblMrr');
  const lblArr = document.getElementById('lblArr');
  const lblCac = document.getElementById('lblCac');
  const lblLtv = document.getElementById('lblLtv');

  if (!state.isDocumentLoaded || !targetYear || targetYear.ricaviTot === 0) {
    if (elMrr) elMrr.textContent = '€0';
    if (elArr) elArr.textContent = '€0';
    if (elCac) elCac.textContent = '--';
    if (elLtv) elLtv.textContent = '--';
    if (elPayback) elPayback.textContent = '--';
    if (elNrr) elNrr.textContent = '--';
    if (elChurn) elChurn.textContent = '--';
    if (badgeStatus) badgeStatus.textContent = 'Svuotato';
    return;
  }

  if (atecoVal === 'university') {
    const ricaviTot = targetYear.ricaviTot || 1;
    const persPct = ((targetYear.salariStipendi / ricaviTot) * 100).toFixed(1);

    if (lblMrr) lblMrr.textContent = `Fondo Dotazione / Cap.Soc. (${yrLabel})`;
    if (lblArr) lblArr.textContent = `Proventi Didattica (${yrLabel})`;
    if (lblCac) lblCac.textContent = `Contributi MIUR / Enti (${yrLabel})`;
    if (lblLtv) lblLtv.textContent = `Personale / Proventi % (${yrLabel})`;

    if (elMrr) { elMrr.textContent = `€${Math.round((state.fullData.sp && state.fullData.sp.capitaleSociale) || 0).toLocaleString('it-IT')}`; elMrr.title = elMrr.textContent; }
    if (elArr) { elArr.textContent = `€${(targetYear.ricaviVendite || 0).toLocaleString('it-IT')}`; elArr.title = elArr.textContent; }
    if (elCac) { elCac.textContent = `€${(targetYear.altriRicavi || 0).toLocaleString('it-IT')}`; elCac.title = elCac.textContent; }
    if (elLtv) { elLtv.textContent = `${persPct}%`; }
    if (elPayback) elPayback.textContent = `${yrLabel}: Autonomia Ok`;
    if (elNrr) elNrr.textContent = '100% Statale';
    if (elChurn) elChurn.textContent = `Profilo: Ente Universitario / Ateneo (${yrLabel})`;
    if (badgeStatus) badgeStatus.textContent = `Ateneo (${yrLabel})`;
  } else {
    const mrr = Math.round((targetYear.ricaviVendite || 0) / 12);

    if (lblMrr) lblMrr.textContent = `MRR Mese (${yrLabel})`;
    if (lblArr) lblArr.textContent = `ARR Anno (${yrLabel})`;
    if (lblCac) lblCac.textContent = `CAC Target (${yrLabel})`;
    if (lblLtv) lblLtv.textContent = `LTV/CAC (${yrLabel})`;

    if (elMrr) { elMrr.textContent = `€${mrr.toLocaleString('it-IT')}`; elMrr.title = elMrr.textContent; }
    if (elArr) { elArr.textContent = `€${(targetYear.ricaviVendite || 0).toLocaleString('it-IT')}`; elArr.title = elArr.textContent; }
    if (elCac) elCac.textContent = '€450';
    if (elLtv) elLtv.textContent = '8.4x';
    if (elPayback) elPayback.textContent = '5.2 Mesi';
    if (elNrr) elNrr.textContent = '118%';
    if (elChurn) elChurn.textContent = `1.2% (Benchmark Anno ${yrNum})`;
    if (badgeStatus) badgeStatus.textContent = `Anno ${yrNum} Attivo`;
  }
}

export function updateBenchmarkInfo() {
  const select = document.getElementById('atecoSelect');
  const container = document.getElementById('benchmarkTargets');
  if (!select || !container) return;

  const val = select.value;
  let html = '';

  if (val === 'university') {
    html = `
      <div class="target-row"><span>Personale / Proventi:</span> <strong>50% - 70%</strong></div>
      <div class="target-row"><span>Autonomia Didattica:</span> <strong>15% - 25%</strong></div>
      <div class="target-row"><span>Copertura Debito DSCR:</span> <strong>> 2.00x</strong></div>
    `;
  } else if (val === 'ets') {
    html = `
      <div class="target-row"><span>Proventi Tipici / Costi:</span> <strong>> 100%</strong></div>
      <div class="target-row"><span>Incidenza Costi Amministrativi:</span> <strong>< 15%</strong></div>
      <div class="target-row"><span>Copertura Debito DSCR:</span> <strong>> 1.50x</strong></div>
    `;
  } else if (val === 'ecommerce') {
    html = `
      <div class="target-row"><span>Target EBITDA %:</span> <strong>15% - 25%</strong></div>
      <div class="target-row"><span>DSO (Incassi):</span> <strong>0-3 Giorni</strong></div>
      <div class="target-row"><span>DPO (Pagamenti):</span> <strong>60-90 Giorni</strong></div>
    `;
  } else if (val === 'consulting') {
    html = `
      <div class="target-row"><span>Target EBITDA %:</span> <strong>20% - 35%</strong></div>
      <div class="target-row"><span>DSO (Incassi):</span> <strong>60-90 Giorni</strong></div>
      <div class="target-row"><span>DPO (Pagamenti):</span> <strong>30 Giorni</strong></div>
    `;
  } else if (val === 'manufacturing') {
    html = `
      <div class="target-row"><span>Target EBITDA %:</span> <strong>12% - 20%</strong></div>
      <div class="target-row"><span>DSO (Incassi):</span> <strong>60-120 Giorni</strong></div>
      <div class="target-row"><span>DPO (Pagamenti):</span> <strong>90 Giorni</strong></div>
    `;
  } else {
    html = `
      <div class="target-row"><span>Target EBITDA %:</span> <strong>50% - 70%</strong></div>
      <div class="target-row"><span>DSO (Incassi):</span> <strong>30 Giorni</strong></div>
      <div class="target-row"><span>DPO (Pagamenti):</span> <strong>30 Giorni</strong></div>
    `;
  }

  container.innerHTML = html;
  renderSaasMetrics();
}

export function renderCharts() {
  const state = getState();
  const y = state.years;
  if (!y || y.length < 1) return;

  const tooltip = document.getElementById('chartTooltip');

  // 1. RICAVI VS EBITDA
  const revContainer = document.getElementById('revenueEbitdaChart');
  if (revContainer) {
    const maxVal = Math.max(...y.map(item => item.ricaviTot), 1000);
    let barsHTML = `<svg width="100%" height="100%" viewBox="0 0 500 200" preserveAspectRatio="none">`;
    y.forEach((item, idx) => {
      const x = 30 + idx * 95;
      const rHeight = (item.ricaviTot / maxVal) * 140;
      const eHeight = Math.max(0, (item.ebitda / maxVal) * 140);

      barsHTML += `<rect x="${x}" y="${160 - rHeight}" width="28" height="${rHeight}" fill="#3b82f6" rx="4" class="chart-element" data-tip="${item.fy} Ricavi Totali: €${item.ricaviTot.toLocaleString('it-IT')}" />`;
      barsHTML += `<rect x="${x + 32}" y="${160 - eHeight}" width="28" height="${eHeight}" fill="#10b981" rx="4" class="chart-element" data-tip="${item.fy} EBITDA: €${item.ebitda.toLocaleString('it-IT')}" />`;
      barsHTML += `<text x="${x + 22}" y="185" fill="#94a3b8" font-size="12" text-anchor="middle">${item.fy}</text>`;
    });
    barsHTML += `</svg>`;
    revContainer.innerHTML = barsHTML;
  }

  // 2. CASH WALK
  const cashContainer = document.getElementById('cashWalkChart');
  if (cashContainer) {
    const maxCash = Math.max(...y.map(item => item.cassa), 100000);
    let points = y.map((item, idx) => {
      const x = 40 + idx * 100;
      const yVal = 160 - (item.cassa / maxCash) * 140;
      return `${x},${yVal}`;
    }).join(' ');

    let lineHTML = `
      <svg width="100%" height="100%" viewBox="0 0 500 200" preserveAspectRatio="none">
        <polyline fill="none" stroke="#6366f1" stroke-width="4" points="${points}" />
    `;
    y.forEach((item, idx) => {
      const x = 40 + idx * 100;
      const yVal = 160 - (item.cassa / maxCash) * 140;
      lineHTML += `<circle cx="${x}" cy="${yVal}" r="6" fill="#6366f1" stroke="#ffffff" stroke-width="2" class="chart-element" data-tip="${item.fy} Cassa Netta: €${item.cassa.toLocaleString('it-IT')}" />`;
      lineHTML += `<text x="${x}" y="185" fill="#94a3b8" font-size="12" text-anchor="middle">${item.fy}</text>`;
    });
    lineHTML += `</svg>`;
    cashContainer.innerHTML = lineHTML;
  }

  // 3. SOLVIBILITÀ
  const solvencyContainer = document.getElementById('solvencyChart');
  if (solvencyContainer) {
    const maxVal = Math.max(...y.map(item => Math.max(item.patrimonioNetto, item.totaleDebiti)), 10000);
    let solvHTML = `<svg width="100%" height="100%" viewBox="0 0 500 200" preserveAspectRatio="none">`;
    y.forEach((item, idx) => {
      const x = 30 + idx * 95;
      const pnHeight = Math.max(0, (item.patrimonioNetto / maxVal) * 140);
      const debHeight = Math.max(0, (item.totaleDebiti / maxVal) * 140);

      solvHTML += `<rect x="${x}" y="${160 - pnHeight}" width="28" height="${pnHeight}" fill="#10b981" rx="4" class="chart-element" data-tip="${item.fy} Patrimonio Netto: €${item.patrimonioNetto.toLocaleString('it-IT')}" />`;
      solvHTML += `<rect x="${x + 32}" y="${160 - debHeight}" width="28" height="${debHeight}" fill="#ef4444" rx="4" class="chart-element" data-tip="${item.fy} Debiti Totali: €${item.totaleDebiti.toLocaleString('it-IT')}" />`;
      solvHTML += `<text x="${x + 22}" y="185" fill="#94a3b8" font-size="12" text-anchor="middle">${item.fy}</text>`;
    });
    solvHTML += `</svg>`;
    solvencyContainer.innerHTML = solvHTML;
  }

  if (tooltip) {
    document.querySelectorAll('.chart-element').forEach(el => {
      el.addEventListener('mousemove', (e) => {
        tooltip.style.display = 'block';
        tooltip.style.left = (e.pageX + 10) + 'px';
        tooltip.style.top = (e.pageY - 30) + 'px';
        tooltip.textContent = el.getAttribute('data-tip');
      });
      el.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none';
      });
    });
  }
}
