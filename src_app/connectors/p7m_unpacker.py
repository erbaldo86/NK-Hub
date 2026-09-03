"""P7M Unpacker for extracting PKCS#7 ASN.1 signed envelopes (.pdf.p7m, .xml.p7m)."""

import logging
from typing import Union
from asn1crypto import cms

logger = logging.getLogger(__name__)


class P7MUnpacker:
    """Extractor for PKCS#7 / CMS ASN.1 envelope signatures (.pdf.p7m, .xml.p7m)."""

    @classmethod
    def is_p7m(cls, input_data: Union[str, bytes]) -> bool:
        """Check if filename extension or header bytes indicate a .p7m PKCS#7 file."""
        if isinstance(input_data, str):
            return input_data.lower().endswith(".p7m")
        
        if isinstance(input_data, bytes):
            if len(input_data) < 4:
                return False
            # Check for ASN.1 DER sequence header 0x30
            if input_data[0] == 0x30:
                try:
                    content_info = cms.ContentInfo.load(input_data)
                    return content_info["content_type"].native == "signed_data"
                except Exception:
                    return False
        return False

    @classmethod
    def unpack_p7m(cls, p7m_bytes: bytes) -> bytes:
        """Extract inner content bytes from a PKCS#7 / CMS signed envelope DER bytes."""
        if not p7m_bytes:
            raise ValueError("Empty p7m bytes provided")

        try:
            content_info = cms.ContentInfo.load(p7m_bytes)
            if content_info["content_type"].native != "signed_data":
                raise ValueError(f"Unsupported PKCS#7 content type: {content_info['content_type'].native}")

            signed_data = content_info["content"]
            encap = signed_data["encap_content_info"]
            
            content_obj = encap["content"]
            if content_obj is None:
                raise ValueError("EncapContentInfo content is empty (detached signature)")

            # native gives extracted Python bytes or data structure
            native_content = content_obj.native
            if isinstance(native_content, bytes):
                return native_content
            
            if hasattr(content_obj, "contents") and isinstance(content_obj.contents, bytes):
                return content_obj.contents

            if isinstance(native_content, str):
                return native_content.encode("utf-8")

            # Fallback to dump bytes if available
            return content_obj.dump()

        except Exception as err:
            logger.warning("asn1crypto unpacking failed: %s. Attempting fallback DER extraction.", err)
            return cls._fallback_der_extraction(p7m_bytes)

    @classmethod
    def _fallback_der_extraction(cls, p7m_bytes: bytes) -> bytes:
        """Fallback method to scan for embedded file payload signatures (PDF, XML, text) inside DER bytes."""
        # PDF magic bytes %PDF-
        pdf_idx = p7m_bytes.find(b"%PDF-")
        if pdf_idx != -1:
            eof_idx = p7m_bytes.rfind(b"%%EOF")
            if eof_idx != -1:
                return p7m_bytes[pdf_idx : eof_idx + 5]
            return p7m_bytes[pdf_idx:]

        # XML magic bytes <?xml
        xml_idx = p7m_bytes.find(b"<?xml")
        if xml_idx != -1:
            gt_idx = p7m_bytes.rfind(b">")
            if gt_idx != -1:
                return p7m_bytes[xml_idx : gt_idx + 1]
            return p7m_bytes[xml_idx:]

        raise ValueError("Could not extract payload from PKCS#7 envelope using fallback scanner.")

    @classmethod
    def unpack_file(cls, file_path: str) -> bytes:
        """Read a .p7m file from disk and return unpacked payload bytes."""
        with open(file_path, "rb") as f:
            data = f.read()
        return cls.unpack_p7m(data)
