"""
Nodo 3 (Chronos & Kairos - CE & SP Engine)
Ground Truth Extractor Module (TB-ST-01 & TB-ST-02 Compliant)
Safely extracts financial ground truth from PDF, ODS, XML, and CSV files.
"""

import sys, os, io, re, asyncio, json
from typing import Dict, Any, Optional

sys.stdout.reconfigure(encoding='utf-8')

async def extract_file_ground_truth_async(file_path: str, timeout_seconds: float = 8.0) -> Dict[str, Any]:
    """
    Extracts ground truth from file using io.BytesIO in memory to avoid WinError 32 lock,
    delegating to asyncio.to_thread with strict timeout cap (TB-ST-01 & TB-ST-02).
    """
    if not os.path.exists(file_path):
        return {"error": f"File non trovato: {file_path}", "isSuccess": False}

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        file_stream = io.BytesIO(file_bytes)
        filename = os.path.basename(file_path)

        task = asyncio.to_thread(_parse_stream_sync, file_stream, filename)
        result = await asyncio.wait_for(task, timeout=timeout_seconds)
        return result
    except asyncio.TimeoutError:
        return {"error": f"Timeout {timeout_seconds}s superato per il file {file_path}", "isSuccess": False}
    except Exception as e:
        return {"error": f"Errore durante estrazione ground truth: {str(e)}", "isSuccess": False}

def _parse_stream_sync(stream: io.BytesIO, filename: str) -> Dict[str, Any]:
    stream.seek(0)
    ext = os.path.splitext(filename)[1].lower()
    
    extracted_data = {
        "filename": filename,
        "isSuccess": True,
        "raw_text_length": 0,
        "ce_found": {},
        "sp_found": {}
    }

    if ext == ".pdf":
        _parse_pdf_stream(stream, extracted_data)
    elif ext == ".ods":
        _parse_ods_stream(stream, extracted_data)
    elif ext in [".xml", ".csv"]:
        _parse_text_stream(stream, extracted_data)

    return extracted_data

def _parse_pdf_stream(stream: io.BytesIO, out: Dict[str, Any]):
    try:
        import pypdf
        reader = pypdf.PdfReader(stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        out["raw_text_length"] = len(text)
        _extract_metrics_from_text(text, out)
    except Exception as e:
        out["error"] = f"PyPDF Exception: {str(e)}"

def _parse_ods_stream(stream: io.BytesIO, out: Dict[str, Any]):
    try:
        import pandas as pd
        df = pd.read_excel(stream, engine="openpyxl" if stream.name.endswith(".xlsx") else None)
        text = df.to_string()
        out["raw_text_length"] = len(text)
        _extract_metrics_from_text(text, out)
    except Exception:
        # Fallback to text decode
        stream.seek(0)
        text = stream.read().decode('utf-8', errors='ignore')
        out["raw_text_length"] = len(text)
        _extract_metrics_from_text(text, out)

def _parse_text_stream(stream: io.BytesIO, out: Dict[str, Any]):
    text = stream.read().decode('utf-8', errors='ignore')
    out["raw_text_length"] = len(text)
    _extract_metrics_from_text(text, out)

def _extract_metrics_from_text(text: str, out: Dict[str, Any]):
    # Extract numerical patterns for CE & SP
    patterns = {
        "ricavi": r"(?:ricavi|valore della produzione)[^\d]*([\d\.,]+)",
        "costi": r"(?:costi della produzione|opex)[^\d]*([\d\.,]+)",
        "ebitda": r"(?:ebitda|margine operativo lordo)[^\d]*([\d\.,]+)",
        "ebit": r"(?:ebit|risultato operativo)[^\d]*([\d\.,]+)",
        "utile": r"(?:utile|risultato dell'esercizio)[^\d]*([\d\.,]+)",
        "attivo": r"(?:totale attivo|totale dell'attivo)[^\d]*([\d\.,]+)",
        "passivo": r"(?:totale passivo|passivo e netto)[^\d]*([\d\.,]+)"
    }
    for k, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val_str = m.group(1).replace(".", "").replace(",", ".")
            try:
                out["ce_found"][k] = float(val_str)
            except ValueError:
                pass
