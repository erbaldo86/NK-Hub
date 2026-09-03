"""PKCS#7 / CAdES-BES (.p7m) Deterministic Unpacker & Signature Inspector.
Nexus Keystone v1.1.0-Universal | LabNK Ingestion Engine.
"""

import re
import base64
from typing import Tuple, Optional, Dict, Any, List
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography import x509


class P7MUnpacker:
    """
    Estrattore deterministico di payload da buste crittografiche .p7m (CAdES-BES / PKCS#7)
    a zero dipendenze CLI esterne con controlli di boundary ASN.1 rigorosi.
    """

    OID_ID_DATA = b"\x2a\x86\x48\x86\xf7\x0d\x01\x07\x01"

    @classmethod
    def unpack(cls, p7m_bytes: bytes) -> Tuple[bytes, Optional[Dict[str, Any]]]:
        """
        Estrae il payload binario originale (es. file PDF) e i metadati della firma digitale.
        Accetta input sia in formato binario DER che in formato Base64 PEM.

        Ritorna:
            Tuple[bytes, Optional[Dict[str, Any]]]: (contenuto_originale, metadati_firma)
        """
        if not p7m_bytes:
            raise ValueError("Payload P7M vuoto o non valido.")

        der_data = cls._normalize_to_der(p7m_bytes)
        signer_info = cls._extract_certificates_info(der_data)
        content = cls._extract_encapsulated_content(der_data)

        return content, signer_info

    @classmethod
    def _normalize_to_der(cls, data: bytes) -> bytes:
        """Rileva se i dati sono in formato PEM Base64 o DER grezzo e restituisce sempre DER."""
        if b"-----BEGIN PKCS7-----" in data or b"-----BEGIN CMS-----" in data:
            pattern = re.compile(rb"-----BEGIN [^-]+-----\s*([A-Za-z0-9+/=\s]+)\s*-----END [^-]+-----")
            match = pattern.search(data)
            if match:
                b64_str = match.group(1).replace(b"\n", b"").replace(b"\r", b"").replace(b" ", b"")
                try:
                    return base64.b64decode(b64_str)
                except Exception:
                    pass

        trimmed = data.strip()
        if len(trimmed) > 4 and re.match(rb"^[A-Za-z0-9+/=\r\n]+$", trimmed[:100]):
            try:
                cleaned = trimmed.replace(b"\n", b"").replace(b"\r", b"").replace(b" ", b"")
                return base64.b64decode(cleaned)
            except Exception:
                pass

        return data

    @classmethod
    def _extract_certificates_info(cls, der_data: bytes) -> Optional[Dict[str, Any]]:
        """Estrae l'elenco e i dettagli dei certificati X.509 presenti nella busta crittografica."""
        try:
            certs = pkcs7.load_der_pkcs7_certificates(der_data)
            if not certs:
                return None

            cert_list: List[Dict[str, Any]] = []
            for cert in certs:
                info = {
                    "subject": cert.subject.rfc4514_string(),
                    "issuer": cert.issuer.rfc4514_string(),
                    "serial_number": str(cert.serial_number),
                    "not_valid_before": cert.not_valid_before_utc.isoformat() if hasattr(cert, 'not_valid_before_utc') else str(cert.not_valid_before),
                    "not_valid_after": cert.not_valid_after_utc.isoformat() if hasattr(cert, 'not_valid_after_utc') else str(cert.not_valid_after),
                    "signature_algorithm_oid": cert.signature_algorithm_oid.dotted_string,
                }
                cert_list.append(info)

            return {
                "certificate_count": len(cert_list),
                "certificates": cert_list,
                "primary_signer": cert_list[0] if cert_list else None
            }
        except Exception:
            return None

    @classmethod
    def _extract_encapsulated_content(cls, der_data: bytes) -> bytes:
        """
        Naviga i tag ASN.1 DER/BER per localizzare ed estrarre il blocco OCTET STRING (tag 0x04)
        incapsulato all'interno della struttura SignedData -> encapContentInfo.
        Include boundary check completi contro stream troncati o malformati.
        """
        idx = der_data.find(cls.OID_ID_DATA)
        if idx == -1:
            pdf_idx = der_data.find(b"%PDF-")
            if pdf_idx != -1:
                return cls._extract_pdf_heuristic(der_data, pdf_idx)
            raise ValueError("Struttura PKCS#7 id-data non trovata nel file .p7m.")

        pos = idx + len(cls.OID_ID_DATA)
        length_total = len(der_data)
        limit = min(length_total, pos + 128)

        while pos < limit and pos < length_total:
            tag = der_data[pos]

            if tag == 0xA0:  # [0] EXPLICIT encapsulation tag
                pos += 1
                if pos >= length_total:
                    break
                pos = cls._skip_asn1_length(der_data, pos)
                continue

            elif tag == 0x04:  # OCTET STRING contenente il payload
                pos += 1
                if pos >= length_total:
                    break
                content_len, content_start = cls._read_asn1_length(der_data, pos)
                if content_len > 0 and (content_start + content_len) <= length_total:
                    extracted = der_data[content_start : content_start + content_len]
                    return extracted
                break

            elif tag == 0x24:  # Constructed OCTET STRING
                pos += 1
                if pos >= length_total:
                    break
                content_len, content_start = cls._read_asn1_length(der_data, pos)
                chunks: List[bytes] = []
                sub_pos = content_start
                end_pos = min(length_total, content_start + content_len) if content_len > 0 else length_total
                while sub_pos < end_pos and sub_pos < length_total and der_data[sub_pos] == 0x04:
                    sub_pos += 1
                    if sub_pos >= length_total:
                        break
                    sub_len, sub_start = cls._read_asn1_length(der_data, sub_pos)
                    if sub_len <= 0 or (sub_start + sub_len) > length_total:
                        break
                    chunks.append(der_data[sub_start : sub_start + sub_len])
                    sub_pos = sub_start + sub_len
                if chunks:
                    return b"".join(chunks)
                break
            else:
                pos += 1

        pdf_idx = der_data.find(b"%PDF-")
        if pdf_idx != -1:
            return cls._extract_pdf_heuristic(der_data, pdf_idx)

        raise ValueError("Impossibile estrarre il payload binario dalla busta PKCS#7.")

    @staticmethod
    def _read_asn1_length(der_bytes: bytes, pos: int) -> Tuple[int, int]:
        """Legge la lunghezza ASN.1 DER con boundary checks (length, data_start_pos)."""
        if pos >= len(der_bytes):
            return -1, pos
        first_byte = der_bytes[pos]
        pos += 1
        if first_byte < 0x80:
            return first_byte, pos
        else:
            num_octets = first_byte & 0x7F
            if num_octets == 0:
                return -1, pos
            if pos + num_octets > len(der_bytes):
                return -1, pos
            length = int.from_bytes(der_bytes[pos : pos + num_octets], "big")
            return length, pos + num_octets

    @staticmethod
    def _skip_asn1_length(der_bytes: bytes, pos: int) -> int:
        """Salta l'header di lunghezza ASN.1 con boundary checks."""
        if pos >= len(der_bytes):
            return len(der_bytes)
        first_byte = der_bytes[pos]
        pos += 1
        if first_byte < 0x80:
            return min(len(der_bytes), pos)
        else:
            num_octets = first_byte & 0x7F
            return min(len(der_bytes), pos + num_octets)

    @staticmethod
    def _extract_pdf_heuristic(der_data: bytes, start_pos: int) -> bytes:
        """Estrae un documento PDF delimitato da '%PDF-' fino a '%%EOF'."""
        eof_marker = b"%%EOF"
        eof_pos = der_data.rfind(eof_marker, start_pos)
        if eof_pos != -1:
            return der_data[start_pos : eof_pos + len(eof_marker)]
        return der_data[start_pos:]
