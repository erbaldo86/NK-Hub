"""LabNK Catalog Seed Loader.
Nexus Keystone v1.1.0-Universal | Zero-Mock Engine.
"""

import json
import logging
from pathlib import Path
from typing import List

from ..models.cgm import CanonicalGrantModel

logger = logging.getLogger("CatalogLoader")

SEED_GRANTS_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_grants.json"


def load_seed_grants() -> List[CanonicalGrantModel]:
    """
    Carica l'elenco dei 38 bandi CGM di riferimento da data/seed_grants.json.
    Valida ogni record contro lo schema CanonicalGrantModel di Pydantic v2.
    """
    if not SEED_GRANTS_PATH.exists():
        logger.error("File seed_grants.json non trovato in %s", SEED_GRANTS_PATH)
        return []

    try:
        with open(SEED_GRANTS_PATH, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        grants: List[CanonicalGrantModel] = []
        for idx, item in enumerate(raw_data):
            try:
                grant = CanonicalGrantModel.model_validate(item, strict=False)
                grants.append(grant)
            except Exception as parse_err:
                logger.warning("Record bando seed #%d non valido: %s", idx, parse_err)

        logger.info("Caricati con successo %d bandi CGM da %s", len(grants), SEED_GRANTS_PATH)
        return grants
    except Exception as exc:
        logger.exception("Errore durante il caricamento di seed_grants.json: %s", exc)
        return []
