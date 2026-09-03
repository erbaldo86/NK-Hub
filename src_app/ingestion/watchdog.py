"""Structural Drift Watchdog & Quality Baseline Verifier.
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

import hashlib
import json
from html.parser import HTMLParser
from typing import Dict, Any, List, Tuple, Optional, Union


class TagSequenceParser(HTMLParser):
    """Estrae la sequenza scheletrica dei soli tag HTML per isolare la struttura dal contenuto."""

    def __init__(self):
        super().__init__()
        self.tag_sequence: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        self.tag_sequence.append(f"<{tag}>")

    def handle_endtag(self, tag: str):
        self.tag_sequence.append(f"</{tag}>")


class StructuralDriftWatchdog:
    """
    Watchdog per il rilevamento del drift strutturale (DOM restyling o mutazione schemi API)
    e per la verifica della completezza dei campi del bando.
    """

    DEFAULT_REQUIRED_FIELDS = [
        "grant_id",
        "title",
        "managing_authority",
        "jurisdiction",
        "source_url"
    ]

    def __init__(self):
        self._source_hashes: Dict[str, str] = {}

    @staticmethod
    def compute_dom_tag_hash(html_content: Union[str, bytes]) -> str:
        """
        Calcola l'hash SHA-256 della sola struttura gerarchica dei tag HTML.
        Ignora attributi variabili (id dinamici, token di sessione, timestamp).
        """
        if isinstance(html_content, bytes):
            html_text = html_content.decode("utf-8", errors="ignore")
        else:
            html_text = html_content

        parser = TagSequenceParser()
        parser.feed(html_text)
        skeleton = "".join(parser.tag_sequence)
        return hashlib.sha256(skeleton.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_json_key_hash(json_payload: Union[str, bytes, Dict[str, Any], List[Any]]) -> str:
        """
        Estrae ricorsivamente l'albero delle chiavi ordinate di un payload JSON
        e ne calcola l'hash SHA-256.
        """
        if isinstance(json_payload, (str, bytes)):
            try:
                data = json.loads(json_payload)
            except Exception:
                data = {}
        else:
            data = json_payload

        def extract_keys(obj: Any) -> Any:
            if isinstance(obj, dict):
                return {k: extract_keys(v) for k, v in sorted(obj.items())}
            elif isinstance(obj, list):
                if len(obj) > 0:
                    return [extract_keys(obj[0])]
                return []
            else:
                return type(obj).__name__

        key_tree = extract_keys(data)
        encoded = json.dumps(key_tree, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def register_baseline_hash(self, source_id: str, baseline_hash: str) -> None:
        """Registra l'hash di baseline per una determinata fonte."""
        self._source_hashes[source_id] = baseline_hash

    def check_drift(self, source_id: str, current_hash: str) -> bool:
        """
        Verifica se l'hash attuale differisce da quello registrato in precedenza.
        Ritorna True se è avvenuto un drift strutturale, False altrimenti.
        """
        if source_id not in self._source_hashes:
            self._source_hashes[source_id] = current_hash
            return False
        return self._source_hashes[source_id] != current_hash

    @classmethod
    def validate_field_completeness(
        cls,
        data: Dict[str, Any],
        required_fields: Optional[List[str]] = None,
        completeness_threshold: float = 0.8
    ) -> Tuple[bool, float, List[str]]:
        """
        Valuta il grado di completezza dei campi obbligatori di un record estratto.
        Ritorna: (is_valid, score_percentuale, campi_mancanti).
        """
        reqs = required_fields or cls.DEFAULT_REQUIRED_FIELDS
        missing = []
        for f in reqs:
            val = data.get(f)
            if val is None or (isinstance(val, (str, list, dict)) and len(val) == 0):
                missing.append(f)

        present_count = len(reqs) - len(missing)
        score = (present_count / len(reqs)) if reqs else 1.0
        is_valid = score >= completeness_threshold
        return is_valid, round(score, 3), missing
