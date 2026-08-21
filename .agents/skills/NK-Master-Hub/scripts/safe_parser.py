import os
import json
from typing import Dict, Any, List
from pydantic import BaseModel, Field

class StructuralAnchorModel(BaseModel):
    """Schema formale rigoroso per l'ancora strutturale memorizzata nel markdown."""
    version: str = Field(..., pattern=r"^v\d+\.\d+\.\d+$")
    project_name: str
    nodes_dependency: Dict[str, List[str]] = Field(
        ..., 
        description="Mappa di dipendenze del DAG: Nodo -> Nodi Genitori/Dipendenze"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

def safe_extract_latent_memory(filepath: str, max_file_size_bytes: int = 2 * 1024 * 1024) -> Dict[str, Any]:
    """
    Esegue un parsing lineare esente da vulnerabilità ReDoS per estrarre
    il blocco <llm_structural_anchor> e lo valida tramite Pydantic.
    """
    try:
        # 1. Protezione da file giganteschi (OOM Protection)
        file_size = os.path.getsize(filepath)
        if file_size > max_file_size_bytes:
            raise ValueError(f"Dimensione del file superiore al limite di sicurezza ({max_file_size_bytes} byte)")

        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 2. Parsing lineare senza Regex per prevenire backtracking catastrofico
        start_tag = "<llm_structural_anchor>"
        end_tag = "</llm_structural_anchor>"
        
        start_idx = content.find(start_tag)
        if start_idx == -1:
            raise ValueError("Tag <llm_structural_anchor> non trovato nel file.")
            
        end_idx = content.find(end_tag, start_idx + len(start_tag))
        if end_idx == -1:
            raise ValueError("Tag di chiusura </llm_structural_anchor> non trovato.")

        json_str = content[start_idx + len(start_tag):end_idx].strip()
        
        # 3. Limite sulla stringa JSON interna (es. max 256KB per l'ancora)
        if len(json_str.encode('utf-8')) > 256 * 1024:
            raise ValueError("La dimensione del blocco JSON dell'ancora supera i 256 KB consentiti.")

        # 4. Deserializzazione
        raw_json = json.loads(json_str)

        # 5. Validazione formale dello Schema con Pydantic
        validated_data = StructuralAnchorModel(**raw_json)
        return validated_data.model_dump()

    except Exception as e:
        # Logging sicuro dell'errore
        print(f"[SECURE PARSER ERROR] Fallimento nel caricamento della memoria latente: {type(e).__name__} - {str(e)}")
        return {}
