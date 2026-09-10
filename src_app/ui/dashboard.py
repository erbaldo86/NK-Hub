"""Interactive Dashboard & Visual Intelligence UI Generator for LabNK.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import json
from pathlib import Path
from typing import Optional

from ..service.bandi_service import LabNKBandiService
from .components.grants_view import render_grants_view
from .components.header import render_header
from .components.kpi_grid import render_kpi_grid
from .components.search_sections import render_search_sections

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
STYLES_PATH = ASSETS_DIR / "styles.css"
CLIENT_JS_PATH = ASSETS_DIR / "dashboard_client.js"


class DashboardRenderer:
    """Generatore di interfaccia utente interattiva e reattiva per la ricerca e consultazione dei bandi."""

    _cached_css: Optional[str] = None
    _cached_js: Optional[str] = None

    @classmethod
    def _load_asset(cls, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    @classmethod
    def get_css(cls) -> str:
        """Restituisce il foglio di stile CSS della dashboard (con cache in-memory)."""
        if cls._cached_css is None:
            cls._cached_css = cls._load_asset(STYLES_PATH)
        return cls._cached_css

    @classmethod
    def get_js(cls) -> str:
        """Restituisce il codice JavaScript client-side (con cache in-memory)."""
        if cls._cached_js is None:
            cls._cached_js = cls._load_asset(CLIENT_JS_PATH)
        return cls._cached_js

    @classmethod
    def render_html(cls, service: LabNKBandiService) -> str:
        """
        Genera una dashboard HTML5 autonoma, moderna e reattiva collegata alle API REST.
        Assembla i componenti modulari (Header, KPI Grid, Search Sections, Grants View),
        iniettando il CSS compilato e il client JavaScript con i dati CGM serializzati.
        """
        grants = service.list_all_grants()
        total_budget = sum(g.budget_totale or 0 for g in grants)
        open_grants = sum(1 for g in grants if g.stato.value == "APERTO")

        grants_json = json.dumps([
            {
                "bando_id": g.bando_id,
                "titolo": g.titolo,
                "ente_erogatore": g.ente_erogatore,
                "descrizione": g.descrizione or "",
                "budget_totale": g.budget_totale or 0,
                "importo_massimo_finanziabile": g.importo_massimo_finanziabile or 0,
                "percentuale_copertura": g.percentuale_copertura or 0,
                "stato": g.stato.value,
                "settori": g.settori_beneficiari or ["TUTTI"],
                "beneficiari": g.tipologia_beneficiari or ["PMI"],
                "regioni": g.regioni_target or ["Tutte"],
                "url_bando": g.url_bando or "#",
                "tipo_agevolazione": g.tipo_agevolazione or "Fondo perduto",
                "fonte_nome": g.fonte_nome or "Fonte Istituzionale",
                "macro_categoria": getattr(g, "macro_categoria", None).value if getattr(g, "macro_categoria", None) else "AGEVOLAZIONE_IMPRESA",
                "data_apertura": g.data_apertura.isoformat() if g.data_apertura else None,
                "data_scadenza": g.data_scadenza.isoformat() if g.data_scadenza else None,
                "de_minimis_applicabile": getattr(g, "de_minimis_applicabile", False),
                "car_codice_misura": getattr(g, "car_codice_misura", None),
                "codice_cup": getattr(g, "codice_cup", None),
            }
            for g in grants
        ], ensure_ascii=False)

        css_content = cls.get_css()
        js_content = cls.get_js()

        header_html = render_header()
        kpi_html = render_kpi_grid(len(grants), open_grants, total_budget)
        search_html = render_search_sections()
        catalog_html = render_grants_view()

        return f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LabNK — Monitoraggio & Intelligence Bandi (Nexus Keystone)</title>
    <style>
{css_content}
    </style>
</head>
<body>
{header_html}

{kpi_html}

{search_html}

{catalog_html}

    <script>
        const GRANTS_DATA = {grants_json};
{js_content}
    </script>
</body>
</html>
"""
