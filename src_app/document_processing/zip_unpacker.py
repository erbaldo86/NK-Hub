"""Safe ZIP Archive Unpacker & Security Gate.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import io
import zipfile
import os
from typing import List, Tuple, Optional


class ZipUnpacker:
    """
    Estrattore sicuro di archivi ZIP con mitigazioni per Zip Bomb (decompression bomb)
    tramite conteggio streaming di byte decompressi e Path Traversal (Zip Slip).
    """

    MAX_TOTAL_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
    MAX_FILE_COUNT = 100
    CHUNK_READ_SIZE = 64 * 1024  # 64 KB streaming buffer
    ALLOWED_EXTENSIONS = {".pdf", ".p7m", ".doc", ".docx", ".txt", ".csv", ".xml", ".json", ".rtf"}

    @classmethod
    def extract_files(
        cls,
        zip_bytes: bytes,
        max_bytes: int = MAX_TOTAL_UNCOMPRESSED_BYTES,
        max_files: int = MAX_FILE_COUNT
    ) -> List[Tuple[str, bytes, str]]:
        """
        Estrae i file contenuti nell'archivio ZIP rispettando i limiti di sicurezza
        con conteggio progressivo dei byte decompressi in streaming.

        Ritorna:
            List[Tuple[str, bytes, str]]: Elenco di (filename, content_bytes, mime_type)
        """
        if not zip_bytes:
            return []

        stream = io.BytesIO(zip_bytes)
        try:
            with zipfile.ZipFile(stream, "r") as zf:
                infolist = zf.infolist()
                if len(infolist) > max_files:
                    raise ValueError(f"Numero di file nell'archivio ({len(infolist)}) eccede il limite ({max_files}).")

                total_uncompressed = 0
                results: List[Tuple[str, bytes, str]] = []

                for info in infolist:
                    # Salta directory
                    if info.is_dir():
                        continue

                    # Prevenzione Zip Slip / Path Traversal
                    filename = os.path.basename(info.filename)
                    if ".." in info.filename or info.filename.startswith(("/", "\\")) or ":" in info.filename:
                        filename = os.path.basename(info.filename.replace("\\", "/"))

                    if not filename:
                        continue

                    # Controllo estensione
                    _, ext = os.path.splitext(filename.lower())
                    if ext not in cls.ALLOWED_EXTENSIONS:
                        continue

                    # Prevenzione Decompression Bomb (controllo preventivo su header)
                    if info.file_size > max_bytes:
                        raise ValueError(
                            f"Dimensione decompressa complessiva supera il limite di sicurezza ({max_bytes} bytes)."
                        )

                    # Estrazione in streaming con conteggio progressivo reale (defense-in-depth)
                    extracted_chunks = bytearray()
                    with zf.open(info, "r") as entry_stream:
                        while True:
                            chunk = entry_stream.read(cls.CHUNK_READ_SIZE)
                            if not chunk:
                                break
                            total_uncompressed += len(chunk)
                            if total_uncompressed > max_bytes:
                                raise ValueError(
                                    f"Dimensione decompressa complessiva supera il limite di sicurezza ({max_bytes} bytes)."
                                )
                            extracted_chunks.extend(chunk)

                    content = bytes(extracted_chunks)
                    mime_type = cls._guess_mime_type(filename)
                    results.append((filename, content, mime_type))

                return results
        except zipfile.BadZipFile as exc:
            raise ValueError(f"Archivio ZIP corrotto o non valido: {str(exc)}")

    @staticmethod
    def _guess_mime_type(filename: str) -> str:
        """Determina il MIME type dall'estensione del file."""
        low = filename.lower()
        if low.endswith(".pdf"):
            return "application/pdf"
        elif low.endswith(".p7m"):
            return "application/pkcs7-mime"
        elif low.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif low.endswith(".doc"):
            return "application/msword"
        elif low.endswith(".xml"):
            return "application/xml"
        elif low.endswith(".json"):
            return "application/json"
        elif low.endswith(".csv"):
            return "text/csv"
        elif low.endswith(".txt"):
            return "text/plain"
        return "application/octet-stream"
