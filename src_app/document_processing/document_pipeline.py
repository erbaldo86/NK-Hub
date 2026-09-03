"""End-to-End Document Processing & Intelligence Pipeline.
Nexus Keystone v1.1.0-Universal | LabNK Bandi Intelligence.
"""

import os
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from .models import ProcessedDocumentReport, BandoSection
from .pdf_extractor import PdfExtractor
from .zip_unpacker import ZipUnpacker
from .section_segmenter import SectionSegmenter
from src_app.ingestion.p7m_unpacker import P7MUnpacker


class DocumentPipeline:
    """
    Pipeline unificata per la gestione completa di allegati complessi di bando:
    P7M Signed Data -> ZIP Extraction -> PDF Text & Metadata Extraction -> Section Segmentation.
    """

    @classmethod
    def process_document(
        cls,
        raw_bytes: bytes,
        filename: str,
        mime_type: Optional[str] = None
    ) -> ProcessedDocumentReport:
        """
        Elabora in cascata un documento grezzo (diretto, compresso in ZIP o firmato in P7M).

        Ritorna:
            ProcessedDocumentReport: Report contenente il testo pulito, metadati e sezioni segmentate.
        """
        if not raw_bytes:
            raise ValueError(f"Payload del documento '{filename}' vuoto.")

        doc_id = hashlib.sha256(raw_bytes).hexdigest()[:16]
        low_fn = filename.lower()
        was_p7m = False
        was_archive = False
        signer_info: Optional[Dict[str, Any]] = None

        current_bytes = raw_bytes
        current_name = filename

        # 1. Step P7M Unpacking
        if low_fn.endswith(".p7m") or (mime_type and "pkcs7" in mime_type.lower()):
            unpacked_content, signer_info = P7MUnpacker.unpack(current_bytes)
            current_bytes = unpacked_content
            was_p7m = True
            if current_name.lower().endswith(".p7m"):
                current_name = current_name[:-4]
            low_fn = current_name.lower()

        extracted_files_count = 1
        total_pages = 0
        text_chunks: List[str] = []
        pdf_metadata: Dict[str, Any] = {}

        # 2. Step ZIP Extraction
        if low_fn.endswith(".zip") or (mime_type and "zip" in mime_type.lower()):
            was_archive = True
            extracted_files = ZipUnpacker.extract_files(current_bytes)
            extracted_files_count = len(extracted_files)

            for sub_name, sub_bytes, sub_mime in extracted_files:
                sub_low = sub_name.lower()
                if sub_low.endswith(".p7m"):
                    sub_bytes, _ = P7MUnpacker.unpack(sub_bytes)
                    sub_name = sub_name[:-4]
                    sub_low = sub_name.lower()

                if sub_low.endswith(".pdf"):
                    pdf_text, meta, pages = PdfExtractor.extract_text_and_meta(sub_bytes)
                    total_pages += pages
                    if pdf_text:
                        text_chunks.append(f"--- Documento: {sub_name} ---\n" + pdf_text)
                    if not pdf_metadata and meta:
                        pdf_metadata = meta
                elif sub_low.endswith((".txt", ".csv", ".xml", ".json")):
                    try:
                        decoded = sub_bytes.decode("utf-8", errors="ignore")
                        text_chunks.append(f"--- Documento: {sub_name} ---\n" + decoded)
                    except Exception:
                        pass

        # 3. Step Single PDF Extraction
        elif low_fn.endswith(".pdf") or (mime_type and "pdf" in mime_type.lower()):
            pdf_text, meta, pages = PdfExtractor.extract_text_and_meta(current_bytes)
            total_pages = pages
            pdf_metadata = meta
            if pdf_text:
                text_chunks.append(pdf_text)

        # 4. Step Plain Text / XML
        else:
            try:
                decoded = current_bytes.decode("utf-8", errors="ignore")
                text_chunks.append(decoded)
            except Exception:
                pass

        full_raw_text = "\n\n".join(text_chunks).strip()

        # 5. Step Section Segmentation & Entity Extraction
        sections = SectionSegmenter.segment_text(full_raw_text)

        consolidated_meta: Dict[str, Any] = {
            "pdf_info": pdf_metadata,
            "signer_info": signer_info
        }

        return ProcessedDocumentReport(
            document_id=f"DOC-{doc_id}",
            source_filename=filename,
            mime_type=mime_type or "application/octet-stream",
            was_p7m=was_p7m,
            was_archive=was_archive,
            extracted_files_count=extracted_files_count,
            total_pages=total_pages or 1,
            total_text_length=len(full_raw_text),
            raw_text=full_raw_text,
            sections=sections,
            metadata=consolidated_meta
        )
