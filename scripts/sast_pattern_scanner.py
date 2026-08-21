"""
SAST Pattern Scanner per NK TAS 3.0 / CRV 3.0 (GATE 2.5).
Scanner deterministico di sicurezza basato su regex ReDoS-safe con quantificatori delimitati.
"""

import sys
import json
import re
import os
from datetime import datetime

SECURITY_PATTERNS = {
    "SQL_INJECTION": {
        "pattern": r'(?:execute|cursor\.execute)\s*\(\s*[f"\'].{0,200}?\{.{0,100}?\}',
        "severity": "CRITICAL",
        "description": "Potenziale SQL injection via concatenazione o f-string nelle query SQL"
    },
    "PATH_TRAVERSAL": {
        "pattern": r'(?:open|Path)\s*\(.{0,200}?\.\.\/\)',
        "severity": "CRITICAL",
        "description": "Rilevato tentativo di Path Traversal (directory escape ../)"
    },
    "HARDCODED_SECRET": {
        "pattern": r'(?:api_key|password|secret|token)\s*=\s*["\'][A-Za-z0-9+/=]{16,}',
        "severity": "HIGH",
        "description": "Potenziale API key o secret hardcoded nel codice sorgente"
    },
    "UNSAFE_DESERIALIZATION": {
        "pattern": r'(?:pickle\.loads|yaml\.unsafe_load|eval\s*\()',
        "severity": "CRITICAL",
        "description": "Rilevata deserializzazione non sicura o esecuzione dinamica eval"
    },
    "INSECURE_RANDOM": {
        "pattern": r'random\.(?:random|randint|choice)\s*\(',
        "severity": "MEDIUM",
        "description": "Uso di generatore casuale non crittografico (usare il modulo secrets)"
    },
    "MISSING_ENCODING": {
        "pattern": r'(?<!\w\.)\bopen\s*\((?![^\)\r\n]*?encoding)[^\)\r\n]+?\)',
        "severity": "MEDIUM",
        "description": "Funzione open() senza specifica esplicita dell'encoding UTF-8 (RULE-10.1)"
    },
    "MISSING_INPUT_VALIDATION": {
        "pattern": r'def\s+(?:handle|endpoint|route|api_|post_|get_|put_|delete_).{0,100}?:\s*\n(?!.*?(?:validate|sanitize|check|assert|raise\s+ValueError))',
        "severity": "HIGH",
        "description": "Funzione handler/endpoint priva di controllo o validazione degli input"
    }
}


def scan_file_for_patterns(file_path: str) -> dict:
    """
    Scansiona un file sorgente applicando i pattern di sicurezza regex.
    """
    if not os.path.exists(file_path):
        return {
            "status": "ERROR",
            "message": f"File non trovato: {file_path}",
            "findings": []
        }

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return {
            "status": "ERROR",
            "message": f"Impossibile leggere il file {file_path}: {str(e)}",
            "findings": []
        }

    findings = []
    lines = content.splitlines()

    for rule_id, rule_info in SECURITY_PATTERNS.items():
        regex = re.compile(rule_info["pattern"], re.MULTILINE | re.IGNORECASE)
        for match in regex.finditer(content):
            # Determina la riga del match
            start_pos = match.start()
            line_no = content[:start_pos].count('\n') + 1
            matched_text = match.group(0).strip()
            
            # Troncamento snippet per token economy
            if len(matched_text) > 120:
                matched_text = matched_text[:117] + "..."

            findings.append({
                "rule_id": rule_id,
                "severity": rule_info["severity"],
                "line": line_no,
                "snippet": matched_text,
                "description": rule_info["description"]
            })

    # Summary
    summary = {
        "CRITICAL": sum(1 for f in findings if f["severity"] == "CRITICAL"),
        "HIGH": sum(1 for f in findings if f["severity"] == "HIGH"),
        "MEDIUM": sum(1 for f in findings if f["severity"] == "MEDIUM"),
        "total": len(findings)
    }

    verdict = "FAIL" if summary["CRITICAL"] > 0 else "PASS"

    return {
        "status": "SUCCESS",
        "verdict": verdict,
        "scan_timestamp": datetime.now().isoformat(),
        "file_scanned": file_path,
        "summary": summary,
        "findings": findings
    }


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        target = sys.argv[1]
        res = scan_file_for_patterns(target)
        print(json.dumps(res, indent=2))
    else:
        print(json.dumps({"status": "INFO", "usage": "python sast_pattern_scanner.py path/to/file.py"}))
