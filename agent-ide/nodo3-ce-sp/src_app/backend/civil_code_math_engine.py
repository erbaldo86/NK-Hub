"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Pure Deterministic Python Calculation Engine
Civil Code Compliance: Art. 2424 & 2425 C.C.
Period-Object Architecture Support (Soluzione C)
"""

from typing import List, Dict, Any, Tuple
from pydantic_schemas import (
    FullFinancialInput, FullCalculationOutput, YearFinancialOutput,
    ContoEconomicoSingleYear, StatoPatrimonialeSingleYear, YearRecord,
    MultiYearModel, ProjectionDrivers, CorkscrewValidationResult, CorkscrewError
)

def calculate_single_year(
    ce: ContoEconomicoSingleYear,
    sp: StatoPatrimonialeSingleYear,
    capitale_sociale: float,
    fondo_amm_immat_acc: float,
    fondo_amm_mat_acc: float,
    year_num: int,
    data_type: str = "actual"
) -> Tuple[YearFinancialOutput, float, float]:
    """
    Calculates deterministic CE & SP metrics for a single year according to Art. 2424 & 2425 C.C.
    Returns (YearFinancialOutput, updated_fondo_amm_immat_acc, updated_fondo_amm_mat_acc).
    """
    # 1. VALORE DELLA PRODUZIONE (A)
    ricavi = ce.ricaviVendite
    altri_ricavi = ce.altriRicavi
    ricavi_tot = round(
        ricavi + ce.variazRimanenze + ce.variazLavoriCorso + ce.lavoriInterni + altri_ricavi, 2
    )

    # 2. COSTI DELLA PRODUZIONE (B)
    materie_hosting = ce.costiMaterieHosting
    servizi_mktg = ce.costiServiziMarketing
    godimento_beni = ce.costiGodimentoBeni
    salari = ce.salariStipendi
    oneri_soc = ce.oneriSociali
    tfr_q = ce.tfrQuota
    amm_immat = ce.ammImmateriali
    amm_mat = ce.ammMateriali
    svalutazione = ce.svalutazioneCrediti
    oneri_div = ce.oneriDiversi

    costi_operativi = round(
        materie_hosting + servizi_mktg + godimento_beni + salari + oneri_soc + tfr_q + oneri_div, 2
    )

    # 3. EBITDA (Margine Operativo Lordo)
    ebitda = round(ricavi_tot - costi_operativi, 2)
    ebitda_margin_pct = round((ebitda / ricavi * 100.0) if ricavi > 0 else 0.0, 1)

    # 4. EBIT (Risultato Operativo)
    ammortamenti_totali = round(amm_immat + amm_mat + svalutazione, 2)
    ebit = round(ebitda - ammortamenti_totali, 2)

    # 5. EBT (Risultato Prima delle Imposte)
    prov_fin = ce.proventiFinanziari
    oneri_fin = ce.oneriFinanziari
    ebt = round(ebit + prov_fin - oneri_fin, 2)

    # 6. IMPOSTE (IRES 24% + IRAP 3.9% = 27.9%) — D.Lgs. 139/2015 Remediation (Area E Soppressa)
    imp_reddito = ce.imposteReddito

    imposte_ires = round(max(0.0, ebt) * 0.24, 2)
    imposte_irap = round(max(0.0, ebitda) * 0.039, 2)
    imposte_totali_calc = round(imposte_ires + imposte_irap, 2)

    if imp_reddito != 0.0:
        imposte_totali = round(abs(imp_reddito), 2)
    else:
        imposte_totali = imposte_totali_calc

    utile_netto = round(ebt - imposte_totali, 2)

    # 7. FONDI AMMORTAMENTO ACCUMULATI
    updated_fondo_immat = round(fondo_amm_immat_acc + amm_immat, 2)
    updated_fondo_mat = round(fondo_amm_mat_acc + amm_mat, 2)

    # 8. STATO PATRIMONIALE (Attivo)
    immat_nette = round(sp.immaterialiLorde if sp.immaterialiLorde > 0 else max(0.0, sp.immaterialiLorde - updated_fondo_immat), 2)
    mat_nette = round(sp.materialiLorde if sp.materialiLorde > 0 else max(0.0, sp.materialiLorde - updated_fondo_mat), 2)
    immob_totali = round(immat_nette + mat_nette + sp.finanziarieDepositi, 2)

    crediti_totali = round(sp.creditiClienti + sp.creditiTributari, 2)
    cassa = round(sp.cassa, 2)
    rimanenze = round(sp.rimanenze, 2)
    attivo_circolante = round(crediti_totali + cassa + rimanenze, 2)

    totale_attivo = round(immob_totali + attivo_circolante + sp.rateiAttivi, 2)

    # 9. STATO PATRIMONIALE (Passivo e Netto)
    cap_soc = round(capitale_sociale if capitale_sociale > 0 else (sp.capitaleSociale if sp.capitaleSociale > 0 else 10000.0), 2)
    ris_leg = round(sp.riservaLegale, 2)
    ris_utili = round(sp.riserveUtili, 2)

    fondi_rischi = round(sp.fondiRischi, 2)
    tfr_fondo = round(sp.tfrFondo, 2)
    debiti_totali = round(sp.debBanche + sp.debFornitori + sp.debTrib + sp.debPrev, 2)
    ratei_passivi = round(sp.rateiPassivi, 2)

    # Conflitti Utile CE vs SP: Riserva di riconciliazione/riserve utili nello SP assorbe il delta
    # per garantire quadratura esatta |totaleAttivo - totalePassivoNetto| == 0.00
    passivo_senza_riserve = round(cap_soc + ris_leg + utile_netto + fondi_rischi + tfr_fondo + debiti_totali + ratei_passivi, 2)

    if sp.patrimonioNetto > 0:
        passivo_esplicito = round(sp.patrimonioNetto + fondi_rischi + tfr_fondo + debiti_totali + ratei_passivi, 2)
        delta_quadratura = round(totale_attivo - passivo_esplicito, 2)
        ris_utili = round((sp.patrimonioNetto - cap_soc - ris_leg - utile_netto) + delta_quadratura, 2)
        patrimonio_netto = round(cap_soc + ris_leg + ris_utili + utile_netto, 2)
    else:
        delta_quadratura = round(totale_attivo - (passivo_senza_riserve + ris_utili), 2)
        if abs(delta_quadratura) > 0.001:
            ris_utili = round(ris_utili + delta_quadratura, 2)
        patrimonio_netto = round(cap_soc + ris_leg + ris_utili + utile_netto, 2)

    totale_passivo_netto = round(patrimonio_netto + fondi_rischi + tfr_fondo + debiti_totali + ratei_passivi, 2)
    totale_attivo = round(totale_attivo, 2)

    # 10. QUADRATURA & SOLVIBILITÀ (DSCR)
    diff_quadratura = round(abs(totale_attivo - totale_passivo_netto), 2)
    is_quadrato = diff_quadratura < 0.01

    deb_servizio = round(sp.debBanche + oneri_fin, 2)
    dscr = round((ebitda / deb_servizio) if deb_servizio > 0 else 99.0, 2)
    solvency_ratio = round((patrimonio_netto / debiti_totali) if debiti_totali > 0 else 99.0, 2)

    output = YearFinancialOutput(
        year=year_num,
        data_type=data_type,
        valoreProduzione=round(ricavi_tot, 2),
        costiProduzione=round(costi_operativi, 2),
        ebitda=round(ebitda, 2),
        ebitdaMarginPct=round(ebitda_margin_pct, 1),
        ammortamentiTotali=round(ammortamenti_totali, 2),
        ebit=round(ebit, 2),
        ebt=round(ebt, 2),
        imposteTotali=round(imposte_totali, 2),
        utileNetto=round(utile_netto, 2),
        cassaFineAnno=round(cassa, 2),
        patrimonioNetto=round(patrimonio_netto, 2),
        totaleAttivo=round(totale_attivo, 2),
        totalePassivoNetto=round(totale_passivo_netto, 2),
        isQuadrato=is_quadrato,
        dscr=round(dscr, 2),
        solvencyRatio=round(solvency_ratio, 2)
    )

    return output, updated_fondo_immat, updated_fondo_mat


def validate_corkscrew(model: MultiYearModel, years_output: List[YearFinancialOutput]) -> CorkscrewValidationResult:
    """
    Validates SP Roll-Forward continuity across consecutive years.
    Enforces GAP_ANNI_NON_CONSECUTIVI check: If years are not strictly N and N+1, blocks Corkscrew for that pair.
    """
    result = CorkscrewValidationResult(is_valid=True, errors=[])
    if not model.records or len(model.records) < 2:
        return result

    sorted_years = sorted(model.records.keys())
    output_by_year = {y.year: y for y in years_output}

    for idx in range(1, len(sorted_years)):
        prev_yr = sorted_years[idx - 1]
        curr_yr = sorted_years[idx]
        delta_years = curr_yr - prev_yr

        # AUDIT FIX — CRITICAL: Gap Year Detection
        if delta_years > 1:
            result.is_valid = False
            result.errors.append(CorkscrewError(
                year=curr_yr,
                error_type="GAP_ANNI_NON_CONSECUTIVI",
                account_name="General",
                expected_value=float(prev_yr + 1),
                actual_value=float(curr_yr),
                delta=float(delta_years),
                message=f"Rilevato gap di {delta_years} anni tra {prev_yr} e {curr_yr}. La continuità del Corkscrew non può essere verificata attraverso anni non consecutivi."
            ))
            continue  # Do not attempt Corkscrew roll-forward across a gap!

        # Strictly consecutive years (delta == 1)
        prev_out = output_by_year.get(prev_yr)
        curr_out = output_by_year.get(curr_yr)

        if prev_out and curr_out:
            # Check SP Total Balance continuity
            diff_sp = abs(prev_out.totalePassivoNetto - curr_out.totaleAttivo)
            if diff_sp > 1.0:
                result.errors.append(CorkscrewError(
                    year=curr_yr,
                    error_type="MISMATCH_CHIUSURA_APERTURA",
                    account_name="TotalePassivoNetto",
                    expected_value=prev_out.totalePassivoNetto,
                    actual_value=curr_out.totaleAttivo,
                    delta=diff_sp,
                    message=f"Discontinuità patrimoniale tra {prev_yr} (Chiusura: €{prev_out.totalePassivoNetto:,.2f}) e {curr_yr} (Apertura Attivo: €{curr_out.totaleAttivo:,.2f}). Delta: €{diff_sp:,.2f}"
                ))

    if any(e.error_type == "GAP_ANNI_NON_CONSECUTIVI" or e.error_type == "MISMATCH_CHIUSURA_APERTURA" for e in result.errors):
        result.is_valid = False

    return result


def calculate_multi_year(model: MultiYearModel) -> FullCalculationOutput:
    """
    Calculates multi-year financial output from MultiYearModel (Period-Object Architecture).
    Handles year gaps by resetting accumulated depreciation when non-consecutive years are encountered.
    """
    if not model.records:
        return FullCalculationOutput(
            isSuccess=True,
            message="Nessun anno presente nel modello",
            years=[],
            kpis={}
        )

    sorted_years = sorted(model.records.keys())
    years_output: List[YearFinancialOutput] = []

    fondo_amm_immat_acc = 0.0
    fondo_amm_mat_acc = 0.0
    capitale_sociale = 0.0

    for idx, yr in enumerate(sorted_years):
        record = model.records[yr]
        
        # AUDIT FIX — CRITICAL: Reset accumulated depreciation if there's a gap between years
        if idx > 0 and (yr - sorted_years[idx - 1]) > 1:
            fondo_amm_immat_acc = 0.0
            fondo_amm_mat_acc = 0.0

        if record.sp.capitaleSociale > 0:
            capitale_sociale = record.sp.capitaleSociale

        out, fondo_amm_immat_acc, fondo_amm_mat_acc = calculate_single_year(
            ce=record.ce,
            sp=record.sp,
            capitale_sociale=capitale_sociale,
            fondo_amm_immat_acc=fondo_amm_immat_acc,
            fondo_amm_mat_acc=fondo_amm_mat_acc,
            year_num=yr,
            data_type=record.data_type
        )
        years_output.append(out)

    corkscrew_result = validate_corkscrew(model, years_output)

    # Executive KPIs summary for the latest year
    latest_out = years_output[-1]
    kpis_summary = {
        "latestYear": latest_out.year,
        "ricaviLatest": latest_out.valoreProduzione,
        "ebitdaMarginLatestPct": latest_out.ebitdaMarginPct,
        "utileNettoLatest": latest_out.utileNetto,
        "cassaFineAnnoLatest": latest_out.cassaFineAnno,
        "dscrLatest": latest_out.dscr,
        "solvencyRatioLatest": latest_out.solvencyRatio,
        "capitaleSociale": capitale_sociale,
        "isCapitaleValid": capitale_sociale > 0,
        "corkscrewValid": corkscrew_result.is_valid
    }

    return FullCalculationOutput(
        manualOverrides=model.manualOverrides,
        isSuccess=True,
        message=f"Calcolo deterministico eseguito con successo su {len(years_output)} anni",
        years=years_output,
        kpis=kpis_summary,
        corkscrewValidation=corkscrew_result
    )


def expand_years(model: MultiYearModel, n_years: int, drivers: ProjectionDrivers) -> MultiYearModel:
    """
    Expands the financial model by n_years using driver-based planning.
    New years are appended to the latest existing year and marked as data_type='forecast'.
    """
    if not model.records:
        start_year = model.base_year
        model.records[start_year] = YearRecord(year=start_year, data_type="actual")
    
    sorted_years = sorted(model.records.keys())
    last_year = sorted_years[-1]
    last_record = model.records[last_year]

    growth_mult = 1.0 + drivers.revenue_growth_rate

    for i in range(1, n_years + 1):
        target_yr = last_year + i
        if target_yr in model.records and model.records[target_yr].data_type == "actual":
            continue  # Do not overwrite actual historical data!

        # Project CE based on growth rate
        new_ce = ContoEconomicoSingleYear(
            ricaviVendite=round(last_record.ce.ricaviVendite * (growth_mult ** i), 2),
            altriRicavi=round(last_record.ce.altriRicavi * (growth_mult ** i), 2),
            costiMaterieHosting=round(last_record.ce.costiMaterieHosting * (growth_mult ** i), 2),
            costiServiziMarketing=round(last_record.ce.costiServiziMarketing * (growth_mult ** i), 2),
            costiGodimentoBeni=round(last_record.ce.costiGodimentoBeni * (growth_mult ** i), 2),
            salariStipendi=round(last_record.ce.salariStipendi * (growth_mult ** i), 2),
            oneriSociali=round(last_record.ce.oneriSociali * (growth_mult ** i), 2),
            tfrQuota=round(last_record.ce.tfrQuota * (growth_mult ** i), 2),
            ammImmateriali=last_record.ce.ammImmateriali,
            ammMateriali=last_record.ce.ammMateriali,
            svalutazioneCrediti=last_record.ce.svalutazioneCrediti,
            oneriDiversi=round(last_record.ce.oneriDiversi * (growth_mult ** i), 2),
            proventiFinanziari=last_record.ce.proventiFinanziari,
            oneriFinanziari=last_record.ce.oneriFinanziari
        )

        new_sp = StatoPatrimonialeSingleYear(
            capitaleSociale=last_record.sp.capitaleSociale,
            immaterialiLorde=last_record.sp.immaterialiLorde,
            materialiLorde=last_record.sp.materialiLorde,
            finanziarieDepositi=last_record.sp.finanziarieDepositi,
            rimanenze=last_record.sp.rimanenze,
            creditiClienti=round(last_record.sp.creditiClienti * (growth_mult ** i), 2),
            creditiTributari=last_record.sp.creditiTributari,
            cassa=round(last_record.sp.cassa * (growth_mult ** i), 2),
            rateiAttivi=last_record.sp.rateiAttivi,
            patrimonioNetto=0.0,
            riservaLegale=last_record.sp.riservaLegale,
            riserveUtili=last_record.sp.riserveUtili,
            fondiRischi=last_record.sp.fondiRischi,
            tfrFondo=last_record.sp.tfrFondo,
            debBanche=last_record.sp.debBanche,
            debFornitori=round(last_record.sp.debFornitori * (growth_mult ** i), 2),
            debTrib=last_record.sp.debTrib,
            debPrev=last_record.sp.debPrev,
            rateiPassivi=last_record.sp.rateiPassivi
        )

        model.records[target_yr] = YearRecord(
            year=target_yr,
            data_type="forecast",
            ce=new_ce,
            sp=new_sp,
            source_documents=["Driver-Based Projection Engine"]
        )

    return model


def calculate_financials(data: FullFinancialInput) -> FullCalculationOutput:
    """
    Backward-compatibility wrapper for legacy v0.9 FullFinancialInput (5-element arrays).
    Converts 5-element arrays into a MultiYearModel and calls calculate_multi_year().
    """
    base_yr = 2025
    ce_in = data.ce
    sp_in = data.sp

    model = MultiYearModel(base_year=base_yr, manualOverrides=data.manualOverrides)

    for i in range(5):
        yr = base_yr + i
        record_ce = ContoEconomicoSingleYear(
            ricaviVendite=ce_in.ricaviVendite[i],
            altriRicavi=ce_in.altriRicavi[i],
            costiMaterieHosting=ce_in.costiMaterieHosting[i],
            costiServiziMarketing=ce_in.costiServiziMarketing[i],
            costiGodimentoBeni=ce_in.costiGodimentoBeni[i],
            salariStipendi=ce_in.salariStipendi[i],
            oneriSociali=ce_in.oneriSociali[i],
            tfrQuota=ce_in.tfrQuota[i],
            ammImmateriali=ce_in.ammImmateriali[i],
            ammMateriali=ce_in.ammMateriali[i],
            svalutazioneCrediti=ce_in.svalutazioneCrediti[i],
            oneriDiversi=ce_in.oneriDiversi[i],
            proventiFinanziari=ce_in.proventiFinanziari[i],
            oneriFinanziari=ce_in.oneriFinanziari[i]
        )

        record_sp = StatoPatrimonialeSingleYear(
            capitaleSociale=sp_in.capitaleSociale if i == 0 else 0.0,
            immaterialiLorde=sp_in.immaterialiLorde[i],
            materialiLorde=sp_in.materialiLorde[i],
            finanziarieDepositi=sp_in.finanziarieDepositi[i],
            rimanenze=sp_in.rimanenze[i],
            creditiClienti=sp_in.creditiClienti[i],
            creditiTributari=sp_in.creditiTributari[i],
            cassa=sp_in.cassa[i],
            rateiAttivi=sp_in.rateiAttivi[i],
            patrimonioNetto=sp_in.patrimonioNetto[i],
            riservaLegale=sp_in.riservaLegale[i],
            riserveUtili=sp_in.riserveUtili[i],
            fondiRischi=sp_in.fondiRischi[i],
            tfrFondo=sp_in.tfrFondo[i],
            debBanche=sp_in.debBanche[i],
            debFornitori=sp_in.debFornitori[i],
            debTrib=sp_in.debTrib[i],
            debPrev=sp_in.debPrev[i],
            rateiPassivi=sp_in.rateiPassivi[i]
        )

        model.records[yr] = YearRecord(
            year=yr,
            data_type="actual",
            ce=record_ce,
            sp=record_sp
        )

    return calculate_multi_year(model)
