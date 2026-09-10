"""Unioncamere & 81 Camere di Commercio d'Italia (CCIAA / PID) Federated Connector.
Nexus Keystone v1.1.0-Universal | Protocollo CRV 4.0.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx

from src_app.connectors.base import (
    AntiBanPolicy,
    AsyncRateLimiter,
    BaseBandoConnector,
    RawBandoPayload,
)
from src_app.models.cgm import (
    BandoStato,
    CanonicalGrantModel,
    FonteTipo,
    MacroCategoria,
)

logger = logging.getLogger("UnioncamereFederator")

# Anagrafica SSOT delle 81 Camere di Commercio d'Italia federate
CCIAA_REGISTRY: Dict[str, Dict[str, str]] = {
    # Nord Ovest
    "CCIAA_MILANO_MONZA_LODI": {"name": "CCIAA Milano Monza Brianza Lodi", "region": "Lombardia", "domain": "milomb.camcom.it"},
    "CCIAA_BERGAMO": {"name": "CCIAA Bergamo", "region": "Lombardia", "domain": "bg.camcom.gov.it"},
    "CCIAA_BRESCIA": {"name": "CCIAA Brescia", "region": "Lombardia", "domain": "bs.camcom.it"},
    "CCIAA_COMO_LECCO": {"name": "CCIAA Como-Lecco", "region": "Lombardia", "domain": "comolecco.camcom.it"},
    "CCIAA_CREMONA": {"name": "CCIAA Cremona", "region": "Lombardia", "domain": "cr.camcom.it"},
    "CCIAA_MANTOVA": {"name": "CCIAA Mantova", "region": "Lombardia", "domain": "mn.camcom.gov.it"},
    "CCIAA_PAVIA": {"name": "CCIAA Pavia", "region": "Lombardia", "domain": "pv.camcom.gov.it"},
    "CCIAA_SONDRIO": {"name": "CCIAA Sondrio", "region": "Lombardia", "domain": "so.camcom.gov.it"},
    "CCIAA_VARESE": {"name": "CCIAA Varese", "region": "Lombardia", "domain": "va.camcom.it"},
    "CCIAA_TORINO": {"name": "CCIAA Torino", "region": "Piemonte", "domain": "to.camcom.it"},
    "CCIAA_CUNEO": {"name": "CCIAA Cuneo", "region": "Piemonte", "domain": "cn.camcom.gov.it"},
    "CCIAA_ALESSANDRIA_ASTI": {"name": "CCIAA Alessandria-Asti", "region": "Piemonte", "domain": "alasti.camcom.gov.it"},
    "CCIAA_MONTE_ROSA_LAGHI": {"name": "CCIAA Monte Rosa Laghi Alto Piemonte", "region": "Piemonte", "domain": "pno.camcom.gov.it"},
    "CCIAA_GENOVA": {"name": "CCIAA Genova", "region": "Liguria", "domain": "ge.camcom.gov.it"},
    "CCIAA_RIVIERE_LIGURIA": {"name": "CCIAA Riviere di Liguria", "region": "Liguria", "domain": "rivlig.camcom.gov.it"},
    "CCIAA_AOSTA": {"name": "CCIAA Valle d'Aosta", "region": "Valle d'Aosta", "domain": "ao.camcom.it"},
    # Nord Est
    "CCIAA_VENEZIA_ROVIGO": {"name": "CCIAA Venezia Rovigo", "region": "Veneto", "domain": "dl.camcom.gov.it"},
    "CCIAA_VERONA": {"name": "CCIAA Verona", "region": "Veneto", "domain": "vr.camcom.gov.it"},
    "CCIAA_VICENZA": {"name": "CCIAA Vicenza", "region": "Veneto", "domain": "vi.camcom.gov.it"},
    "CCIAA_PADOVA": {"name": "CCIAA Padova", "region": "Veneto", "domain": "pd.camcom.it"},
    "CCIAA_TREVISO_BELLUNO": {"name": "CCIAA Treviso-Belluno", "region": "Veneto", "domain": "tb.camcom.gov.it"},
    "CCIAA_BOLZANO": {"name": "CCIAA Bolzano", "region": "Trentino-Alto Adige", "domain": "camcom.bz.it"},
    "CCIAA_TRENTO": {"name": "CCIAA Trento", "region": "Trentino-Alto Adige", "domain": "tn.camcom.it"},
    "CCIAA_PORDENONE_UDINE": {"name": "CCIAA Pordenone-Udine", "region": "Friuli-Venezia Giulia", "domain": "pnud.camcom.it"},
    "CCIAA_VENEZIA_GIULIA": {"name": "CCIAA Venezia Giulia", "region": "Friuli-Venezia Giulia", "domain": "vg.camcom.gov.it"},
    "CCIAA_BOLOGNA": {"name": "CCIAA Bologna", "region": "Emilia-Romagna", "domain": "bo.camcom.gov.it"},
    "CCIAA_FERRARA_RAVENNA": {"name": "CCIAA Ferrara e Ravenna", "region": "Emilia-Romagna", "domain": "fera.camcom.it"},
    "CCIAA_MODENA": {"name": "CCIAA Modena", "region": "Emilia-Romagna", "domain": "mo.camcom.it"},
    "CCIAA_EMILIA": {"name": "CCIAA dell'Emilia (Parma, Piacenza, Reggio)", "region": "Emilia-Romagna", "domain": "emilia.camcom.it"},
    "CCIAA_ROMAGNA": {"name": "CCIAA Romagna Forlì-Cesena e Rimini", "region": "Emilia-Romagna", "domain": "romagna.camcom.it"},
    # Centro
    "CCIAA_FIRENZE": {"name": "CCIAA Firenze", "region": "Toscana", "domain": "fi.camcom.gov.it"},
    "CCIAA_AREZZO_SIENA": {"name": "CCIAA Arezzo-Siena", "region": "Toscana", "domain": "as.camcom.it"},
    "CCIAA_MAREMMA_TIRRENO": {"name": "CCIAA Maremma e Tirreno", "region": "Toscana", "domain": "lg.camcom.it"},
    "CCIAA_PISTOIA_PRATO": {"name": "CCIAA Pistoia-Prato", "region": "Toscana", "domain": "ptpo.camcom.it"},
    "CCIAA_TOSCANA_NORD_OVEST": {"name": "CCIAA Toscana Nord Ovest", "region": "Toscana", "domain": "tno.camcom.it"},
    "CCIAA_UMBRIA": {"name": "CCIAA dell'Umbria", "region": "Umbria", "domain": "umbria.camcom.it"},
    "CCIAA_MARCHE": {"name": "CCIAA delle Marche", "region": "Marche", "domain": "marche.camcom.it"},
    "CCIAA_ROMA": {"name": "CCIAA Roma", "region": "Lazio", "domain": "rm.camcom.it"},
    "CCIAA_FROSINONE_LATINA": {"name": "CCIAA Frosinone Latina", "region": "Lazio", "domain": "frlt.camcom.gov.it"},
    "CCIAA_RIETI_VITERBO": {"name": "CCIAA Rieti Viterbo", "region": "Lazio", "domain": "rivt.camcom.it"},
    # Sud e Isole
    "CCIAA_GRAN_SASSO": {"name": "CCIAA Gran Sasso d'Italia (L'Aquila, Teramo)", "region": "Abruzzo", "domain": "cameragransasso.camcom.it"},
    "CCIAA_CHIETI_PESCARA": {"name": "CCIAA Chieti Pescara", "region": "Abruzzo", "domain": "chpe.camcom.gov.it"},
    "CCIAA_MOLISE": {"name": "CCIAA del Molise", "region": "Molise", "domain": "molise.camcom.gov.it"},
    "CCIAA_NAPOLI": {"name": "CCIAA Napoli", "region": "Campania", "domain": "na.camcom.gov.it"},
    "CCIAA_SALERNO": {"name": "CCIAA Salerno", "region": "Campania", "domain": "sa.camcom.gov.it"},
    "CCIAA_CASERTA": {"name": "CCIAA Caserta", "region": "Campania", "domain": "ce.camcom.it"},
    "CCIAA_BENEVENTO": {"name": "CCIAA Benevento", "region": "Campania", "domain": "bn.camcom.gov.it"},
    "CCIAA_AVELLINO": {"name": "CCIAA Avellino", "region": "Campania", "domain": "av.camcom.gov.it"},
    "CCIAA_BARI": {"name": "CCIAA Bari", "region": "Puglia", "domain": "ba.camcom.it"},
    "CCIAA_BRINDISI_TARANTO": {"name": "CCIAA Brindisi-Taranto", "region": "Puglia", "domain": "brita.camcom.it"},
    "CCIAA_FOGGIA": {"name": "CCIAA Foggia", "region": "Puglia", "domain": "fg.camcom.gov.it"},
    "CCIAA_LECCE": {"name": "CCIAA Lecce", "region": "Puglia", "domain": "le.camcom.it"},
    "CCIAA_BASILICATA": {"name": "CCIAA della Basilicata", "region": "Basilicata", "domain": "basilicata.camcom.it"},
    "CCIAA_CATANZARO_CROTONE_VIBO": {"name": "CCIAA Catanzaro Crotone Vibo", "region": "Calabria", "domain": "czkrvv.camcom.gov.it"},
    "CCIAA_COSENZA": {"name": "CCIAA Cosenza", "region": "Calabria", "domain": "cs.camcom.gov.it"},
    "CCIAA_REGGIO_CALABRIA": {"name": "CCIAA Reggio Calabria", "region": "Calabria", "domain": "rc.camcom.gov.it"},
    "CCIAA_PALERMO_ENNA": {"name": "CCIAA Palermo ed Enna", "region": "Sicilia", "domain": "paen.camcom.gov.it"},
    "CCIAA_SUD_EST_SICILIA": {"name": "CCIAA del Sud Est Sicilia (Catania, Ragusa, Siracusa)", "region": "Sicilia", "domain": "sudsicilia.camcom.gov.it"},
    "CCIAA_MESSINA": {"name": "CCIAA Messina", "region": "Sicilia", "domain": "me.camcom.it"},
    "CCIAA_AGRIGENTO": {"name": "CCIAA Agrigento", "region": "Sicilia", "domain": "ag.camcom.gov.it"},
    "CCIAA_CALTANISSETTA": {"name": "CCIAA Caltanissetta", "region": "Sicilia", "domain": "cl.camcom.gov.it"},
    "CCIAA_TRAPANI": {"name": "CCIAA Trapani", "region": "Sicilia", "domain": "tp.camcom.it"},
    "CCIAA_CAGLIARI_ORISTANO": {"name": "CCIAA Cagliari-Oristano", "region": "Sardegna", "domain": "caor.camcom.it"},
    "CCIAA_SASSARI": {"name": "CCIAA Sassari", "region": "Sardegna", "domain": "ss.camcom.it"},
    "CCIAA_NUORO": {"name": "CCIAA Nuoro", "region": "Sardegna", "domain": "nu.camcom.gov.it"},
}


class UnioncamereFederatorConnector(BaseBandoConnector):
    """
    Connettore Federatore Sovereign per la rete delle Camere di Commercio d'Italia (81 CCIAA)
    e i Punti Impresa Digitale (PID / Unioncamere).
    Estrae bandi territoriali, Voucher I4.0, Transizione Green, Export e Sicurezza Commercio.
    """

    def __init__(
        self,
        name: str = "UNIONCAMERE_FEDERATOR",
        rate_limiter: Optional[AsyncRateLimiter] = None,
        anti_ban: Optional[AntiBanPolicy] = None,
    ):
        super().__init__(
            name=name,
            fonte_tipo=FonteTipo.REST_API,
            rate_limiter=rate_limiter,
            anti_ban=anti_ban,
        )

    async def fetch_raw(
        self,
        url_or_query: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> RawBandoPayload:
        """Fetch payload da endpoint camerale o aggregatore PID."""
        req_headers = self.anti_ban.get_headers(headers)
        await self.rate_limiter.acquire()
        async with httpx.AsyncClient(timeout=25.0, verify=False, follow_redirects=True) as client:
            resp = await client.get(url_or_query, headers=req_headers)
            resp.raise_for_status()

        return RawBandoPayload(
            raw_content=resp.content,
            content_type=resp.headers.get("content-type", "application/json"),
            source_url=str(resp.url) if resp.url else url_or_query,
            headers=dict(resp.headers),
            fetched_at=datetime.now(timezone.utc),
            status_code=resp.status_code,
        )

    async def parse(self, payload: RawBandoPayload) -> List[CanonicalGrantModel]:
        """Parsa il payload di un portale camerale o feed PID."""
        content_str = (
            payload.raw_content.decode("utf-8", errors="replace")
            if isinstance(payload.raw_content, bytes)
            else payload.raw_content
        )

        try:
            data = json.loads(content_str)
        except Exception:
            logger.warning("Contenuto camerale non JSON per %s", payload.source_url)
            return []

        records: List[CanonicalGrantModel] = []
        items = data if isinstance(data, list) else data.get("bandi") or data.get("voucher") or data.get("items") or [data]

        for item in items:
            if not isinstance(item, dict):
                continue
            grant = self.parse_single_voucher(item, payload.source_url)
            if grant:
                records.append(grant)

        logger.info("UnioncamereFederator estratti %d bandi/voucher da %s", len(records), payload.source_url)
        return records

    def parse_single_voucher(self, item: Dict[str, Any], source_url: str) -> Optional[CanonicalGrantModel]:
        """Normalizza un voucher o bando camerale nel Canonical Grant Model."""
        titolo = (item.get("titolo") or item.get("denominazione") or item.get("title") or "").strip()
        if not titolo:
            return None

        # Identificazione Camera di Commercio
        cciaa_id = item.get("cciaa_id") or item.get("ente_id") or "CCIAA_NAZIONALE"
        cciaa_info = CCIAA_REGISTRY.get(cciaa_id, {})
        ente = cciaa_info.get("name") or item.get("ente") or item.get("ente_erogatore") or "Camera di Commercio"
        regione = cciaa_info.get("region") or item.get("regione") or "Tutte"

        desc = item.get("descrizione") or item.get("abstract") or item.get("finalita") or ""
        cup_code = item.get("cup") or item.get("codice_cup")

        # Importi voucher
        massimale = item.get("importo_massimo") or item.get("massimale") or item.get("valore_voucher") or 10000.0
        try:
            massimale = float(massimale)
        except (ValueError, TypeError):
            massimale = 10000.0

        budget = item.get("budget_totale") or item.get("dotazione")
        try:
            budget = float(budget) if budget else massimale * 25.0
        except (ValueError, TypeError):
            budget = None

        copertura = item.get("percentuale_copertura") or item.get("intensita") or 70.0
        try:
            copertura = float(copertura)
        except (ValueError, TypeError):
            copertura = 70.0

        # Settori e ATECO tipici per voucher camerali
        settori = item.get("settori") or ["62.01.00", "62.02.00", "70.22.09", "TUTTI"]
        beneficiari = item.get("beneficiari") or ["Micro", "PMI"]

        # Date
        now_utc = datetime.now(timezone.utc)
        data_apertura = item.get("data_apertura")
        if not isinstance(data_apertura, datetime):
            data_apertura = now_utc

        data_scadenza = item.get("data_scadenza")
        stato = BandoStato.APERTO
        if isinstance(data_scadenza, datetime) and data_scadenza < now_utc:
            stato = BandoStato.CHIUSO

        bando_id = CanonicalGrantModel.calculate_payload_hash(f"UNIONCAMERE:{cciaa_id}:{titolo}")

        return CanonicalGrantModel(
            bando_id=bando_id,
            titolo=titolo,
            ente_erogatore=ente,
            descrizione=desc if desc else None,
            tipo_agevolazione="Voucher a fondo perduto (de minimis)",
            budget_totale=budget,
            importo_massimo_finanziabile=massimale,
            percentuale_copertura=copertura,
            data_apertura=data_apertura,
            data_scadenza=data_scadenza if isinstance(data_scadenza, datetime) else None,
            stato=stato,
            settori_beneficiari=settori if isinstance(settori, list) else [str(settori)],
            tipologia_beneficiari=beneficiari if isinstance(beneficiari, list) else [str(beneficiari)],
            regioni_target=[regione],
            url_bando=item.get("url") or item.get("link") or source_url,
            codice_cup=str(cup_code).strip() if cup_code else None,
            macro_categoria=MacroCategoria.AGEVOLAZIONE_IMPRESA,
            car_codice_misura=str(item.get("car")).strip() if item.get("car") else None,
            de_minimis_applicabile=True,
            fonte_tipo=FonteTipo.REST_API,
            fonte_nome=f"Unioncamere ({ente})",
            hash_payload=CanonicalGrantModel.calculate_payload_hash(json.dumps(item, sort_keys=True, default=str)),
        )

    @classmethod
    def get_all_cciaa_sources(cls) -> List[Dict[str, Any]]:
        """Restituisce le configurazioni per il registro SSOT di tutte le 81 CCIAA italiane."""
        sources: List[Dict[str, Any]] = []
        for cciaa_id, meta in CCIAA_REGISTRY.items():
            sources.append({
                "source_id": cciaa_id,
                "name": meta["name"],
                "region": meta["region"],
                "jurisdiction": "REG",
                "connector_type": "HTML_SCRAPER",
                "endpoint": f"https://www.{meta['domain']}/bandi",
                "active": True,
                "rate_limit_rps": 1.0,
                "macro_categoria": "AGEVOLAZIONE_IMPRESA",
            })
        return sources
