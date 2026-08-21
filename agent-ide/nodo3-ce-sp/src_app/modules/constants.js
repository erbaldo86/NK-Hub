// 🏛️ CONSTANTS & TAXONOMY DICTIONARY - NODO 3 (ES6 Module)
// D.Lgs. 139/2015 Compliance & Complete Accounting Mappings

export const MAX_ACTIVE_FILES = 4;
export const MAX_VISIBLE_YEARS = 5;
export const MAX_FILE_SIZE_BYTES = 52428800; // 50MB (50 * 1024 * 1024)

export const CE_KEYS = [
  'ricaviVendite', 'variazRimanenze', 'variazLavoriCorso', 'lavoriInterni', 'altriRicavi',
  'costiMaterieHosting', 'costiServiziMarketing', 'costiGodimentoBeni', 'salariStipendi',
  'oneriSociali', 'tfrQuota', 'ammImmateriali', 'ammMateriali', 'svalutazioneCrediti',
  'oneriDiversi', 'proventiFinanziari', 'oneriFinanziari', 'proventiStraordinari',
  'imposteReddito', 'imposteIres', 'imposteIrap'
];

export const SP_KEYS = [
  'capitaleSociale', 'immaterialiLorde', 'materialiLorde', 'finanziarieDepositi',
  'rimanenze', 'creditiClienti', 'creditiTributari', 'cassa', 'rateiAttivi',
  'patrimonioNetto', 'riservaLegale', 'riserveUtili', 'fondiRischi', 'tfrFondo',
  'debBanche', 'debFornitori', 'debTrib', 'debPrev', 'rateiPassivi'
];

export const TAXONOMY_LABELS = {
  // Conto Economico
  ricaviVendite: 'A.1) Ricavi delle vendite e delle prestazioni',
  variazRimanenze: 'A.2) Variazioni delle rimanenze di prodotti',
  variazLavoriCorso: 'A.3) Variazioni dei lavori in corso su ordinazione',
  lavoriInterni: 'A.4) Incrementi di immobilizzazioni per lavori interni',
  altriRicavi: 'A.5) Altri ricavi e proventi',
  costiMaterieHosting: 'B.6) Per materie prime, sussidiarie, di consumo e merci',
  costiServiziMarketing: 'B.7) Per servizi',
  costiGodimentoBeni: 'B.8) Per godimento di beni di terzi',
  salariStipendi: 'B.9.a) Salari e stipendi',
  oneriSociali: 'B.9.b) Oneri sociali',
  tfrQuota: 'B.9.c) Trattamento di fine rapporto',
  ammImmateriali: 'B.10.a) Ammortamento delle immobilizzazioni immateriali',
  ammMateriali: 'B.10.b) Ammortamento delle immobilizzazioni materiali',
  svalutazioneCrediti: 'B.10.d) Svalutazioni dei crediti compresi nell’attivo circolante',
  oneriDiversi: 'B.14) Oneri diversi di gestione',
  proventiFinanziari: 'C.15/16) Proventi finanziari',
  oneriFinanziari: 'C.17) Interessi e altri oneri finanziari',
  imposteReddito: '20) Imposte sul reddito dell’esercizio',

  // Stato Patrimoniale - Attivo
  immaterialiLorde: 'B.I) Immobilizzazioni immateriali',
  materialiLorde: 'B.II) Immobilizzazioni materiali',
  finanziarieDepositi: 'B.III) Immobilizzazioni finanziarie',
  rimanenze: 'C.I) Rimanenze',
  creditiClienti: 'C.II.1) Verso clienti',
  creditiTributari: 'C.II.5-bis) Crediti tributari',
  cassa: 'C.IV) Disponibilità liquide',
  rateiAttivi: 'D) Ratei e risconti attivi',

  // Stato Patrimoniale - Passivo
  capitaleSociale: 'A.I) Capitale',
  riservaLegale: 'A.IV) Riserva legale',
  riserveUtili: 'A.VIII) Utili (perdite) portati a nuovo',
  patrimonioNetto: 'A) Patrimonio Netto',
  fondiRischi: 'B) Fondi per rischi e oneri',
  tfrFondo: 'C) Trattamento di fine rapporto di lavoro subordinato',
  debBanche: 'D.4) Debiti verso banche',
  debFornitori: 'D.7) Debiti verso fornitori',
  debTrib: 'D.12) Debiti tributari',
  debPrev: 'D.13) Debiti verso istituti di previdenza e di sicurezza sociale',
  rateiPassivi: 'E) Ratei e risconti passivi'
};

export const CATEGORY_GROUP_META = {
  ricavi: { title: '📈 Valore della Produzione & Proventi MIUR / ETS (A.1 - A.5)', icon: '📈' },
  opex: { title: '📉 Costi della Produzione & Ammortamenti (B.6 - B.14)', icon: '📉' },
  finance: { title: '⚖️ Proventi, Oneri Finanziari & Imposte (C, D, E, 20)', icon: '⚖️' },
  attivoFisso: { title: '🏢 Immobilizzazioni & Attivo Fisso (SP B.I - B.III)', icon: '🏢' },
  attivoCircolante: { title: '💰 Attivo Circolante & Disponibilità Liquide (SP C.I - C.IV)', icon: '💰' },
  passivoDebiti: { title: '📋 Passivo, Patrimonio Netto & Debiti (SP Passivo B - D)', icon: '📋' },
  altre: { title: '⚙️ Altre Voci da Mappare', icon: '⚙️' }
};

export function getCategoryGroupKey(mapping) {
  if (['ricaviVendite', 'variazRimanenze', 'variazLavoriCorso', 'lavoriInterni', 'altriRicavi'].includes(mapping)) return 'ricavi';
  if (['costiMaterieHosting', 'costiServiziMarketing', 'costiGodimentoBeni', 'salariStipendi', 'oneriSociali', 'tfrQuota', 'ammImmateriali', 'ammMateriali', 'svalutazioneCrediti', 'oneriDiversi'].includes(mapping)) return 'opex';
  if (['proventiFinanziari', 'oneriFinanziari', 'proventiStraordinari', 'imposteReddito'].includes(mapping)) return 'finance';
  if (['immaterialiLorde', 'materialiLorde', 'finanziarieDepositi'].includes(mapping)) return 'attivoFisso';
  if (['rimanenze', 'creditiClienti', 'creditiTributari', 'cassa', 'rateiAttivi'].includes(mapping)) return 'attivoCircolante';
  if (['capitaleSociale', 'riservaLegale', 'riserveUtili', 'patrimonioNetto', 'tfrFondo', 'debBanche', 'debFornitori', 'debTrib', 'debPrev', 'fondiRischi', 'rateiPassivi'].includes(mapping)) return 'passivoDebiti';
  return 'altre';
}

export function getMappingSelectOptions(selectedMapping) {
  return `
  <optgroup label="Conto Economico (C.C. Art. 2425)">
    <option value="ricaviVendite" ${selectedMapping === 'ricaviVendite' ? 'selected' : ''}>A.1 Ricavi delle Vendite e Prestazioni</option>
    <option value="variazRimanenze" ${selectedMapping === 'variazRimanenze' ? 'selected' : ''}>A.2 Variazioni Rimanenze (Prodotti in corso/finiti)</option>
    <option value="variazLavoriCorso" ${selectedMapping === 'variazLavoriCorso' ? 'selected' : ''}>A.3 Variazioni Lavori in Corso su Ordinazione</option>
    <option value="lavoriInterni" ${selectedMapping === 'lavoriInterni' ? 'selected' : ''}>A.4 Incrementi Immobilizzazioni per Lavori Interni</option>
    <option value="altriRicavi" ${selectedMapping === 'altriRicavi' ? 'selected' : ''}>A.5 Altri Ricavi e Proventi (Contributi/R&S)</option>
    <option value="costiMaterieHosting" ${selectedMapping === 'costiMaterieHosting' ? 'selected' : ''}>B.6 Materie Prime, Sussidiarie & Hosting</option>
    <option value="costiServiziMarketing" ${selectedMapping === 'costiServiziMarketing' ? 'selected' : ''}>B.7 Servizi & Consulenze/Marketing</option>
    <option value="costiGodimentoBeni" ${selectedMapping === 'costiGodimentoBeni' ? 'selected' : ''}>B.8 Godimento Beni Terzi (Affitti/Licenze)</option>
    <option value="salariStipendi" ${selectedMapping === 'salariStipendi' ? 'selected' : ''}>B.9.a Salari e Stipendi Personale</option>
    <option value="oneriSociali" ${selectedMapping === 'oneriSociali' ? 'selected' : ''}>B.9.b Oneri Sociali (INPS/INAIL)</option>
    <option value="tfrQuota" ${selectedMapping === 'tfrQuota' ? 'selected' : ''}>B.9.c Quota TFR Esercizio</option>
    <option value="ammImmateriali" ${selectedMapping === 'ammImmateriali' ? 'selected' : ''}>B.10.a Ammortamento Immobilizzazioni Immateriali</option>
    <option value="ammMateriali" ${selectedMapping === 'ammMateriali' ? 'selected' : ''}>B.10.b Ammortamento Immobilizzazioni Materiali</option>
    <option value="svalutazioneCrediti" ${selectedMapping === 'svalutazioneCrediti' ? 'selected' : ''}>B.10.c Svalutazione Crediti Commerciali</option>
    <option value="oneriDiversi" ${selectedMapping === 'oneriDiversi' ? 'selected' : ''}>B.14 Oneri Diversi di Gestione</option>
    <option value="proventiFinanziari" ${selectedMapping === 'proventiFinanziari' ? 'selected' : ''}>C.16 Proventi Finanziari</option>
    <option value="oneriFinanziari" ${selectedMapping === 'oneriFinanziari' ? 'selected' : ''}>C.17 Interessi ed Oneri Finanziari</option>
    <option value="proventiStraordinari" ${selectedMapping === 'proventiStraordinari' ? 'selected' : ''}>[LEGACY] E.20 Proventi Straordinari (Ex Area E)</option>
    <option value="imposteReddito" ${selectedMapping === 'imposteReddito' ? 'selected' : ''}>20. Imposte sul Reddito (IRAP/IRES)</option>
  </optgroup>
  <optgroup label="Tassonomia Università / MIUR & Non-Profit">
    <option value="ricaviVendite" ${selectedMapping === 'ricaviVendite' ? 'selected' : ''}>MIUR A.I.1 Proventi Didattica (Tasse/Contributi)</option>
    <option value="ricaviVendite" ${selectedMapping === 'ricaviVendite' ? 'selected' : ''}>MIUR A.I.2 Proventi Ricerche Commissionate & Tech Transfer</option>
    <option value="ricaviVendite" ${selectedMapping === 'ricaviVendite' ? 'selected' : ''}>MIUR A.I.3 Proventi Ricerche Competitivi (PRIN/Horizon)</option>
    <option value="altriRicavi" ${selectedMapping === 'altriRicavi' ? 'selected' : ''}>MIUR A.II Contributi MIUR / FFO e Amministrazioni Centrali</option>
    <option value="altriRicavi" ${selectedMapping === 'altriRicavi' ? 'selected' : ''}>ETS RUNTS Proventi da Attività di Interesse Generale</option>
  </optgroup>
  <optgroup label="Stato Patrimoniale - Attivo (Art. 2424)">
    <option value="immaterialiLorde" ${selectedMapping === 'immaterialiLorde' ? 'selected' : ''}>B.I Immobilizzazioni Immateriali Nette</option>
    <option value="materialiLorde" ${selectedMapping === 'materialiLorde' ? 'selected' : ''}>B.II Immobilizzazioni Materiali Nette</option>
    <option value="finanziarieDepositi" ${selectedMapping === 'finanziarieDepositi' ? 'selected' : ''}>B.III Immobilizzazioni Finanziarie</option>
    <option value="rimanenze" ${selectedMapping === 'rimanenze' ? 'selected' : ''}>C.I Rimanenze di Magazzino</option>
    <option value="creditiClienti" ${selectedMapping === 'creditiClienti' ? 'selected' : ''}>C.II Crediti Commerciali ed Istituzionali</option>
    <option value="creditiTributari" ${selectedMapping === 'creditiTributari' ? 'selected' : ''}>C.II.5 Crediti Tributari e IVA a Credito</option>
    <option value="cassa" ${selectedMapping === 'cassa' ? 'selected' : ''}>C.IV Cassa e Disponibilità Liquide</option>
    <option value="rateiAttivi" ${selectedMapping === 'rateiAttivi' ? 'selected' : ''}>D) Ratei e Risconti Attivi</option>
  </optgroup>
  <optgroup label="Stato Patrimoniale - Passivo (Art. 2424)">
    <option value="capitaleSociale" ${selectedMapping === 'capitaleSociale' ? 'selected' : ''}>A.I Capitale Sociale / Fondo Dotazione</option>
    <option value="riservaLegale" ${selectedMapping === 'riservaLegale' ? 'selected' : ''}>A.IV Riserva Legale</option>
    <option value="riserveUtili" ${selectedMapping === 'riserveUtili' ? 'selected' : ''}>A.VIII Riserve di Utili e Straordinarie</option>
    <option value="fondiRischi" ${selectedMapping === 'fondiRischi' ? 'selected' : ''}>B) Fondi Rischi ed Oneri</option>
    <option value="tfrFondo" ${selectedMapping === 'tfrFondo' ? 'selected' : ''}>C) Fondo Trattamento di Fine Rapporto (TFR)</option>
    <option value="debBanche" ${selectedMapping === 'debBanche' ? 'selected' : ''}>D.4 Debiti verso Banche ed Istituti Finanziari</option>
    <option value="debFornitori" ${selectedMapping === 'debFornitori' ? 'selected' : ''}>D.7 Debiti verso Fornitori</option>
    <option value="debTrib" ${selectedMapping === 'debTrib' ? 'selected' : ''}>D.12 Debiti Tributari (IRES/IRAP/IVA)</option>
    <option value="debPrev" ${selectedMapping === 'debPrev' ? 'selected' : ''}>D.13 Debiti verso Istituti Previdenziali</option>
    <option value="rateiPassivi" ${selectedMapping === 'rateiPassivi' ? 'selected' : ''}>E) Ratei e Risconti Passivi / Contributi Investimenti</option>
  </optgroup>
  `;
}

export function getYearSelectOptions(selectedYear, baseYear = 2025) {
  const base = parseInt(baseYear, 10) || 2025;
  const curYr = parseInt(selectedYear, 10) || base;
  let html = '';
  for (let y = base - 4; y <= base + 8; y++) {
    const label = y === base ? `Anno ${y} (Base)` : `Anno ${y}`;
    html += `<option value="${y}" ${curYr === y ? 'selected' : ''}>${label}</option>`;
  }
  return html;
}

export const DEFAULT_METRICS_CONFIG = {
  saas: {
    grossMarginThreshold: 0.70,
    ebitdaThreshold: 0.20,
    cacPaybackMaxMonths: 18,
    ltvCacMinRatio: 3.0
  }
};

export function formatEuro(val) {
  if (val === undefined || val === null || isNaN(val)) return '€ 0';
  return new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(val);
}

export function formatPercent(val) {
  if (val === undefined || val === null || isNaN(val)) return '0.0%';
  return `${(val * 100).toFixed(1)}%`;
}
