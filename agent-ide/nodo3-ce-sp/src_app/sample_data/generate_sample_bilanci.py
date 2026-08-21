import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

OUTPUT_DIR = r"g:\Il mio Drive\Antigravity\agent-ide\nodo3-ce-sp\sample_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def create_pdf_bilancio(filename, company_name, vat_num, year, data):
    filepath = os.path.join(OUTPUT_DIR, filename)
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E293B'),
        alignment=1,
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B'),
        alignment=1,
        spaceAfter=15
    )

    sec_heading = ParagraphStyle(
        'SecHeading',
        parent=styles['Heading2'],
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#0F172A'),
        spaceBefore=12,
        spaceAfter=6
    )

    cell_style = ParagraphStyle('Cell', fontSize=9, leading=11, textColor=colors.HexColor('#334155'))
    cell_bold = ParagraphStyle('CellBold', fontSize=9, leading=11, textColor=colors.HexColor('#0F172A'), fontName='Helvetica-Bold')
    cell_right = ParagraphStyle('CellRight', fontSize=9, leading=11, textColor=colors.HexColor('#0F172A'), alignment=2, fontName='Helvetica-Bold')

    story = []

    # Header
    story.append(Paragraph(f"<b>{company_name}</b>", title_style))
    story.append(Paragraph(f"Codice Fiscale / P.IVA: {vat_num} — Sede Legale: Milano (MI)<br/><b>STATO PATRIMONIALE E CONTO ECONOMICO AL 31/12/{year}</b> (Art. 2424 e 2425 C.C.)", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563EB'), spaceAfter=15))

    # STATO PATRIMONIALE
    story.append(Paragraph("<b>STATO PATRIMONIALE</b>", sec_heading))

    sp_table_data = [
        [Paragraph("<b>ATTIVO</b>", cell_bold), Paragraph(f"<b>Esercizio {year} (€)</b>", cell_right)],
        [Paragraph("<b>A) IMMOBILIZZAZIONI</b>", cell_bold), Paragraph(f"€ {data['sp_immob_tot']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;I IMMATERIALI", cell_style), Paragraph(f"€ {data['sp_immat']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;II MATERIALI", cell_style), Paragraph(f"€ {data['sp_mat']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;III FINANZIARIE", cell_style), Paragraph(f"€ {data['sp_fin']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>B) ATTIVO CIRCOLANTE</b>", cell_bold), Paragraph(f"€ {data['sp_circ_tot']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;I RIMANENZE", cell_style), Paragraph(f"€ {data['sp_rimanenze']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;II CREDITI", cell_style), Paragraph(f"€ {data['sp_crediti']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;IV DISPONIBILITA LIQUIDE", cell_style), Paragraph(f"€ {data['sp_cassa']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>C) RATEI E RISCONTI ATTIVI</b>", cell_bold), Paragraph(f"€ {data['sp_ratei_attivi']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>TOTALE ATTIVO</b>", cell_bold), Paragraph(f"<b>€ {data['sp_totale_attivo']:,.2f}</b>".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>PASSIVO E PATRIMONIO NETTO</b>", cell_bold), Paragraph("", cell_right)],
        [Paragraph("<b>A) PATRIMONIO NETTO</b>", cell_bold), Paragraph(f"€ {data['sp_patrimonio_netto']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;I CAPITALE SOCIALE", cell_style), Paragraph(f"€ {data['sp_capitale_sociale']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>B) FONDI PER RISCHI ED ONERI</b>", cell_bold), Paragraph(f"€ {data['sp_fondi_rischi']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>C) TRATTAMENTO DI FINE RAPPORTO</b>", cell_bold), Paragraph(f"€ {data['sp_tfr']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>D) DEBITI</b>", cell_bold), Paragraph(f"€ {data['sp_debiti']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>E) RATEI E RISCONTI PASSIVI</b>", cell_bold), Paragraph(f"€ {data['sp_ratei_passivi']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>TOTALE PASSIVO E PATRIMONIO NETTO</b>", cell_bold), Paragraph(f"<b>€ {data['sp_totale_passivo']:,.2f}</b>".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
    ]

    t_sp = Table(sp_table_data, colWidths=[340, 180])
    t_sp.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (0,11), (-1,11), colors.HexColor('#F1F5F9')),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#CBD5E1')),
        ('LINEBELOW', (0,10), (-1,10), 1.5, colors.HexColor('#0F172A')),
        ('LINEBELOW', (0,18), (-1,18), 1.5, colors.HexColor('#0F172A')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_sp)

    story.append(Spacer(1, 15))

    # CONTO ECONOMICO
    story.append(Paragraph("<b>CONTO ECONOMICO</b>", sec_heading))

    ce_table_data = [
        [Paragraph("<b>VOCE DI BILANCIO</b>", cell_bold), Paragraph(f"<b>Esercizio {year} (€)</b>", cell_right)],
        [Paragraph("<b>A) PROVENTI OPERATIVI</b>", cell_bold), Paragraph(f"€ {data['ce_proventi_tot']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;I. PROVENTI PROPRI / RICAVI DELLE VENDITE", cell_style), Paragraph(f"€ {data['ce_ricavi']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>B) COSTI OPERATIVI</b>", cell_bold), Paragraph(f"€ {data['ce_costi_tot']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;VIII. COSTI DEL PERSONALE", cell_style), Paragraph(f"€ {data['ce_personale']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;IX. COSTI DELLA GESTIONE CORRENTE", cell_style), Paragraph(f"€ {data['ce_gestione']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;X. AMMORTAMENTI E SVALUTAZIONI", cell_style), Paragraph(f"€ {data['ce_ammortamenti']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>DIFFERENZA TRA VALORE E COSTI DELLA PRODUZIONE (A - B)</b>", cell_bold), Paragraph(f"€ {data['ce_ebit']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>C) PROVENTI E ONERI FINANZIARI</b>", cell_bold), Paragraph(f"€ {data['ce_finanziari_netti']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;1) Proventi finanziari", cell_style), Paragraph(f"€ {data['ce_prov_fin']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;2) Interessi ed altri oneri finanziari", cell_style), Paragraph(f"€ {data['ce_oneri_fin']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>E) PROVENTI ED ONERI STRAORDINARI</b>", cell_bold), Paragraph(f"€ {data['ce_straordinari']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>F) IMPOSTE SUL REDDITO DELL'ESERCIZIO</b>", cell_bold), Paragraph(f"€ {data['ce_imposte']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
        [Paragraph("<b>RISULTATO DI ESERCIZIO (UTILE NETTO)</b>", cell_bold), Paragraph(f"<b>€ {data['ce_utile_netto']:,.2f}</b>".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_right)],
    ]

    t_ce = Table(ce_table_data, colWidths=[340, 180])
    t_ce.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
        ('LINEBELOW', (0,0), (-1,0), 1, colors.HexColor('#CBD5E1')),
        ('LINEBELOW', (0,13), (-1,13), 1.5, colors.HexColor('#0F172A')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(t_ce)

    doc.build(story)
    print(f"[OK] Generato PDF: {filepath}")

def create_txt_bilancio(filename, company_name, vat_num, year, data):
    filepath = os.path.join(OUTPUT_DIR, filename)
    txt_content = f"""
================================================================================
{company_name}
Codice Fiscale / P.IVA: {vat_num}
STATO PATRIMONIALE E CONTO ECONOMICO AL 31/12/{year} (Art. 2424 e 2425 C.C.)
================================================================================

STATO PATRIMONIALE

A) IMMOBILIZZAZIONI € {data['sp_immob_tot']:,.2f}
I IMMATERIALI € {data['sp_immat']:,.2f}
II MATERIALI € {data['sp_mat']:,.2f}
III FINANZIARIE € {data['sp_fin']:,.2f}

B) ATTIVO CIRCOLANTE € {data['sp_circ_tot']:,.2f}
I RIMANENZE € {data['sp_rimanenze']:,.2f}
II CREDITI € {data['sp_crediti']:,.2f}
IV DISPONIBILITA LIQUIDE € {data['sp_cassa']:,.2f}

C) RATEI E RISCONTI ATTIVI € {data['sp_ratei_attivi']:,.2f}

TOTALE ATTIVO € {data['sp_totale_attivo']:,.2f}


PASSIVO E PATRIMONIO NETTO

A) PATRIMONIO NETTO € {data['sp_patrimonio_netto']:,.2f}
I CAPITALE SOCIALE € {data['sp_capitale_sociale']:,.2f}
B) FONDI PER RISCHI ED ONERI € {data['sp_fondi_rischi']:,.2f}
C) TRATTAMENTO DI FINE RAPPORTO € {data['sp_tfr']:,.2f}
D) DEBITI € {data['sp_debiti']:,.2f}
E) RATEI E RISCONTI PASSIVI € {data['sp_ratei_passivi']:,.2f}

TOTALE PASSIVO E PATRIMONIO NETTO € {data['sp_totale_passivo']:,.2f}


CONTO ECONOMICO

A) PROVENTI OPERATIVI € {data['ce_proventi_tot']:,.2f}
I. PROVENTI PROPRI € {data['ce_ricavi']:,.2f}

B) COSTI OPERATIVI € {data['ce_costi_tot']:,.2f}
VIII. COSTI DEL PERSONALE € {data['ce_personale']:,.2f}
IX. COSTI DELLA GESTIONE CORRENTE € {data['ce_gestione']:,.2f}
X. AMMORTAMENTI E SVALUTAZIONI € {data['ce_ammortamenti']:,.2f}

C) PROVENTI E ONERI FINANZIARI € {data['ce_finanziari_netti']:,.2f}
1) Proventi finanziari € {data['ce_prov_fin']:,.2f}
2) Interessi ed altri oneri finanziari € {data['ce_oneri_fin']:,.2f}

E) PROVENTI ED ONERI STRAORDINARI € {data['ce_straordinari']:,.2f}
F) IMPOSTE SUL REDDITO DELL'ESERCIZIO € {data['ce_imposte']:,.2f}

RISULTATO DI ESERCIZIO € {data['ce_utile_netto']:,.2f}
================================================================================
""".replace(',', 'X').replace('.', ',').replace('X', '.')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(txt_content.strip())
    print(f"[OK] Generato TXT: {filepath}")

# Datasets
data_alfa = {
    'sp_immat': 120000.0, 'sp_mat': 850000.0, 'sp_fin': 50000.0, 'sp_immob_tot': 1020000.0,
    'sp_rimanenze': 210000.0, 'sp_crediti': 430000.0, 'sp_cassa': 380000.0, 'sp_circ_tot': 1020000.0,
    'sp_ratei_attivi': 15000.0, 'sp_totale_attivo': 2055000.0,
    'sp_capitale_sociale': 500000.0, 'sp_patrimonio_netto': 850000.0,
    'sp_fondi_rischi': 45000.0, 'sp_tfr': 85000.0, 'sp_debiti': 980000.0, 'sp_ratei_passivi': 95000.0,
    'sp_totale_passivo': 2055000.0,
    'ce_proventi_tot': 2570000.0, 'ce_ricavi': 2450000.0,
    'ce_costi_tot': 2080000.0, 'ce_personale': 820000.0, 'ce_gestione': 1150000.0, 'ce_ammortamenti': 110000.0,
    'ce_ebit': 490000.0, 'ce_finanziari_netti': -16000.0, 'ce_prov_fin': 12000.0, 'ce_oneri_fin': 28000.0,
    'ce_straordinari': 0.0, 'ce_imposte': -140000.0, 'ce_utile_netto': 334000.0
}

data_beta = {
    'sp_immat': 450000.0, 'sp_mat': 180000.0, 'sp_fin': 20000.0, 'sp_immob_tot': 650000.0,
    'sp_rimanenze': 15000.0, 'sp_crediti': 290000.0, 'sp_cassa': 1250000.0, 'sp_circ_tot': 1555000.0,
    'sp_ratei_attivi': 8000.0, 'sp_totale_attivo': 2213000.0,
    'sp_capitale_sociale': 200000.0, 'sp_patrimonio_netto': 1350000.0,
    'sp_fondi_rischi': 20000.0, 'sp_tfr': 38000.0, 'sp_debiti': 740000.0, 'sp_ratei_passivi': 65000.0,
    'sp_totale_passivo': 2213000.0,
    'ce_proventi_tot': 2200000.0, 'ce_ricavi': 1850000.0,
    'ce_costi_tot': 1825000.0, 'ce_personale': 950000.0, 'ce_gestione': 780000.0, 'ce_ammortamenti': 95000.0,
    'ce_ebit': 375000.0, 'ce_finanziari_netti': -13000.0, 'ce_prov_fin': 5000.0, 'ce_oneri_fin': 18000.0,
    'ce_straordinari': 25000.0, 'ce_imposte': -95000.0, 'ce_utile_netto': 292000.0
}

data_gamma = {
    'sp_immat': 35000.0, 'sp_mat': 420000.0, 'sp_fin': 15000.0, 'sp_immob_tot': 470000.0,
    'sp_rimanenze': 680000.0, 'sp_crediti': 510000.0, 'sp_cassa': 190000.0, 'sp_circ_tot': 1380000.0,
    'sp_ratei_attivi': 12000.0, 'sp_totale_attivo': 1862000.0,
    'sp_capitale_sociale': 100000.0, 'sp_patrimonio_netto': 580000.0,
    'sp_fondi_rischi': 15000.0, 'sp_tfr': 62000.0, 'sp_debiti': 1150000.0, 'sp_ratei_passivi': 55000.0,
    'sp_totale_passivo': 1862000.0,
    'ce_proventi_tot': 3880000.0, 'ce_ricavi': 3800000.0,
    'ce_costi_tot': 3618000.0, 'ce_personale': 640000.0, 'ce_gestione': 2920000.0, 'ce_ammortamenti': 58000.0,
    'ce_ebit': 262000.0, 'ce_finanziari_netti': -32000.0, 'ce_prov_fin': 2000.0, 'ce_oneri_fin': 34000.0,
    'ce_straordinari': -10000.0, 'ce_imposte': -65000.0, 'ce_utile_netto': 155000.0
}

if __name__ == '__main__':
    create_pdf_bilancio("Bilancio_Simulato_Alfa_Spa.pdf", "AZIENDA INDUSTRIALE ALFA S.P.A.", "01234567890", "2024", data_alfa)
    create_pdf_bilancio("Bilancio_Simulato_Beta_Tech.pdf", "BETA TECH STARTUP S.R.L.", "09876543210", "2024", data_beta)
    create_pdf_bilancio("Bilancio_Simulato_Gamma_Retail.pdf", "GAMMA RETAIL & LOGISTICS S.R.L.", "05554443322", "2024", data_gamma)
    
    create_txt_bilancio("Bilancio_Simulato_Alfa_Spa.txt", "AZIENDA INDUSTRIALE ALFA S.P.A.", "01234567890", "2024", data_alfa)
    create_txt_bilancio("Bilancio_Simulato_Beta_Tech.txt", "BETA TECH STARTUP S.R.L.", "09876543210", "2024", data_beta)
