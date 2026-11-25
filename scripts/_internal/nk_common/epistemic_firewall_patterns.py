# -*- coding: utf-8 -*-
"""Pattern pure-stdlib e redazione PII/secret per l'Epistemic Firewall."""

from __future__ import annotations

import re
import urllib.parse
from typing import Dict, Tuple

HANDOFF_V2_START_PASSIVE: str = "[NK-ANCHOR:START:HANDOFF_V2:PASSIVE_STANDBY]"
HANDOFF_V2_END_PASSIVE: str = "[NK-ANCHOR:END:HANDOFF_V2:PASSIVE_STANDBY]"
HANDOFF_V2_START_ACTIVE: str = "[NK-ANCHOR:START:HANDOFF_V2:ACTIVE_CONTINUATION]"
HANDOFF_V2_END_ACTIVE: str = "[NK-ANCHOR:END:HANDOFF_V2:ACTIVE_CONTINUATION]"
T12_START: str = "[NK-ANCHOR:START:PASSIVE_STATE_HANDOFF]"
T12_END: str = "[NK-ANCHOR:END:PASSIVE_STATE_HANDOFF]"
T12_HEADER_PREFIX: str = "# [HANDOFF STATO SESSIONE NK-HUB] (Template 12: PASSIVE_SESSION_STATE_HANDOFF)"

_ZERO_WIDTH_TRANS = str.maketrans("", "", "\u200b\u200c\u200d\u2060\ufeff")
_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})([^\n`~]*)$")
_NEUTRAL_FENCE_LANGS = frozenset(("", "text", "txt", "plain", "log", "diff"))
_SHA256_HEX64_RE = re.compile(r"\b[0-9a-fA-F]{64}\b")
_T12_ALWAYS_BLOCKED_SMUGGLE_RE = re.compile(r"(?:(?:^|\s)!(?:diretto|raw)\b|<directive>|<env_capsule>|^\s*#{1,4}\s*(?:FASE|PHASE|MACRO[- ]?FASE|LIVELLO)\s*[1-9]\d*)", re.IGNORECASE)
_T12_STANDALONE_SMUGGLE_RE = re.compile(r"(?:(?:^|\s)!(?:diretto|raw)\b|\b(?:INTRINSIC_GOAL|INTRINSIC_PLAN|INTRINSIC_BOOST|invoke_subagent|define_subagent|ask_question)\b|<directive>|<env_capsule>|^\s*#{1,4}\s*(?:FASE|PHASE|MACRO[- ]?FASE|LIVELLO)\s*[1-9]\d*)", re.IGNORECASE)
_DESTRUCTIVE_SHELL_RE = re.compile(r"(?:\brm\s+-[rf]{1,2}\b|\bremove-item\b|\brmdir\s+/s\b|\bdrop\s+(?:table|database)\b|\bdelete\s+from\b)", re.IGNORECASE)
_HANDOFF_MUTATING_ORDER_RE = re.compile(r"(?:\b(?:cancella(?:re)?|elimina(?:re)?|rimuovi|rimuovere|sovrascrivi|sovrascrivere|formatta(?:re)?|drop\s+table|delete\s+from|set-content|remove-item|out-file|write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content|win32_atomic_replace)\b|(?<![A-Za-z0-9_-])--promote-staging\b)", re.IGNORECASE)
_PROHIBITION_LINE_RE = re.compile(r"\b(?:vieta(?:to|ndo|re)?|divieto|proibit[oa]|non\s+(?:attivare|invocare|generare|eseguire|proporre|avviare|modificare|devi|impone)|mai\s+(?:attivare|invocare)|nessun[oa]?\s+(?:pista|task|opzione))\b", re.IGNORECASE)
_AP12_IMPERATIVE_LEAK_RE = re.compile(r"\b(?:INTRINSIC_GOAL|INTRINSIC_PLAN|INTRINSIC_BOOST|invoke_subagent|define_subagent|ask_question)\b|(?:^|\n)\s*#{1,4}\s*(?:FASE|PHASE|MACRO[- ]?FASE|LIVELLO)\s*[1-9]\d*", re.IGNORECASE)
_AP13_COGNITIVE_TUNNELING_RE = re.compile(
    r"(?:\b(?:Pista|Track)\s+(?:[1-9]\d*[A-Z]?|[A-D])\b"
    r"|\bOpzione\s+[A-D1-9](?:\s+da\s+accettare|\s*:|\b(?=\s*[-:]))"
    r"|\bOption\s+[A-D1-9]\s*:"
    r"|\bSeleziona\s+quale\s+(?:task|pista|opzione)\s+avviare\b"
    r"|\bScegli\s+(?:(?:quale\s+)?(?:pista|task|opzione)|tra\s+[A-D1-9]\s+e\s+[A-D1-9])\b"
    r"|\b(?:Choose|Select|Pick)\s+(?:which\s+(?:track|task|option)|(?:between\s+)?(?:option|track|task)\s+[A-D1-9]\b|[A-D]\s+or\s+[A-D]\b)"
    r"|\bTask\s+[1-9]\d*\s*:)",
    re.IGNORECASE,
)
_CLAUSE_BREAK_RE = re.compile(r"\s*(?:;|&&|\|\||(?<!\b\d)(?<!\.\d)\.(?=\s+[A-ZÀ-ÿ<#!\w]))\s*")
_OUTBOUND_HANDOFF_RE = re.compile(r"^\s*(?:per\s+favore\s+|please\s+|ora\s+|adesso\s+|mi\s+)?(?:fammi|fammene|fai|dammi|voglio|crea(?:mi)?|genera(?:mi)?|prepara(?:mi)?|compila(?:mi)?|salva(?:mi)?|esegui|produci|serializza|emetti|make|create|generate|prepare|build|compile|serialize)\s+(?:un[oa]?\s+|il\s+|a\s+|an\s+|the\s+)?(?:nuov[oa]\s+|new\s+)?(?:passive\s+|active\s+|state\s+|session\s+)?handoff\b", re.IGNORECASE)
_OUTBOUND_CODE_EXCLUSION_RE = re.compile(r"(?:\.(?:py|ts|tsx|js|jsx|md|json|yaml|yml|toml|sql|sh|ps1)\b|(?:scripts|tests|src_app|nk_genome|\.staging|\.agents)[/\\]|\b(?:implementa(?:re)?|modifica(?:re)?|fix(?:a|are)?|debug(?:ga|gare)?|refactor(?:ing)?|scrivi|scrivere|aggiungi|rimuovi|elimina(?:re)?|cancella(?:re)?|testa(?:re)?|verifica(?:re)?|analizza(?:re)?|spiega(?:re)?|progetta(?:re)?|router|architettura|bug|errore|codice|code|funzione|classe|modulo|script|schema|pytest|endpoint|api|database|sql|componente|frontend|backend|file)\b)", re.IGNORECASE)
_AGENT_DIRECTIVE_CUE_RE = re.compile(r"(?:opera\s+come|agisci\s+come|\bsei\s+\[?\d+\]?|invoke_subagent|define_subagent|<directive>|<env_capsule>|<system|!diretto|\bRULE-[A-Z0-9._-]+|\b(?:FASE|PHASE|MACRO[- ]?FASE|PASSO|TASK)\s*\d+\b|esegui\s+questo\s+piano|delega\s+a\b)", re.IGNORECASE)
_OUTBOUND_SHELL_RE = re.compile(r"(?:;|&&|\|\||\||`|\$\(|>>|<<|\b(?:rm\s+-rf|rmdir|remove-item|del\s+|drop\s+table|delete\s+from|set-content|out-file|git\s+reset|git\s+push)\b)", re.IGNORECASE)
_OUTBOUND_ACTIVE_CUE_RE = re.compile(r"\b(?:attiv[oa]|active|active_continuation|continuazione|continuation|con\s+staging|with\s+staging|include\s+staging)\b", re.IGNORECASE)
_PEM_KEY_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|(?=\n\n)|\Z)")
_DSN_PASS_RE = re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb|redis|amqp|smtp)s?(?:\+[a-z0-9_]+)?://[^:\s\"'`<>]*:(?!\[REDACTED_SECRET\])[^\s@\"'`<>]+@[^\s\"'`<>]+", re.IGNORECASE)
_HTTP_CRED_RE = re.compile(r"\bhttps?://[^:\s\"'`<>/?#]+:(?!\[REDACTED_SECRET\])[^\s@\"'`<>/?#]+@[^\s\"'`<>]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"\bBearer\s+(?!\[REDACTED_SECRET\])[A-Za-z0-9._~+/-]{10,}=*", re.IGNORECASE)
_SECRET_PREFIX_RE = re.compile(r"\b(?:sk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[0-9A-Za-z-]{10,}|AKIA[0-9A-Z]{16})\b")
_KV_SECRET_RE = re.compile(
    r'(?i)(["\']?\b(?:api_key|apikey|oauth_token|access_token|refresh_token|client_secret|smtp_pass(?:word)?|db_pass(?:word)?|'
    r'secret_key|password|passwd|db_pwd|user_pwd|smtp_pwd|jwt_secret|private_key|auth_token|signing_key|webhook_secret)\b["\']?\s*)([:=])(\s*)(["\']?)'
    r'(?!\[REDACTED_SECRET\]|<[^>]+>|YOUR_[A-Z_]+|\$\{?[A-Z0-9_]+\}?|None\b|null\b|true\b|false\b|str\b|Optional\b|'
    r'os\.environ\b|(?:os\.)?getenv\(|request\.|self\.|settings\.|config\.|Field\(|env\.)([^\s"\',;}\])]{6,})(["\']?)'
)
_EMAIL_RE = re.compile(r"\b(?!git@[A-Za-z0-9.-]+:)([A-Za-z0-9._%+-]+@((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}|localhost))\b(?!:[A-Za-z0-9_./~-])")
_PHONE_CTX_RE = re.compile(r"((?:tel:|whatsapp:|wa\.me/|\b(?:tel|telefono|phone|cell|cellulare|mobile|whatsapp|wa)(?:\s*[:=]\s*|\s+)))(\+?\d[\d\s().-]{6,18}\d)", re.IGNORECASE)
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAFE_DOMAINS = ("localhost", "example.com", "example.org", "example.net", "test.local", "invalid", "json-schema.org", "w3.org", "www.w3.org")
_DSN_ANY_RE = re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb|redis|amqp|smtp)s?(?:\+[a-z0-9_]+)?://([^\s\"'`<>/?#]+)", re.IGNORECASE)
_HTTP_URL_RE = re.compile(r"\bhttps?://([^/\s\"'`<>?#]+)([^\s\"'`<>]*)", re.IGNORECASE)
_LIVE_URL_HINT_RE = re.compile(r"(?:/api/|/v\d+/|/webhook|/oauth|/token|/graphql|hooks\.slack\.com|discord\.com/api/webhooks|^(?:api|webhook|prod|live|smtp|mail)\.|[?&](?:key|token|api_key)=|\b\d{1,3}(?:\.\d{1,3}){3}\b)", re.IGNORECASE)
_AP14_COMMON_CONTAM_RE = re.compile(
    r'(?:"?(?:tool_calls|toolCalls|tool_results|toolResults|tool_call_id|function_call|plannerResponse|planner_response|thinkingProcess|thinking_process|reasoning_content)"?\s*:|'
    r'"status"\s*:\s*"RUNNING"|"(?:transcript_raw_jsonl_included|failed_reasoning_included)"\s*:\s*true\b|\b(?:failed_reasoning|raw_transcript|transcript_jsonl|transcript_raw_jsonl|thought_signature|transient_task)\b|'
    r'\btask-\d+\b[^\n]{0,80}\b(?:RUNNING|WORKING|PENDING)\b|\battendo\s+il\s+completamento\b|</?SYSTEM_MESSAGE>|</?USER_REQUEST>|<CONTEXT_SUMMARY>|<subagent_reminder>|<task_boundary>|<strict_boundaries>|'
    r'<user_information>|\.system_generated[/\\]logs[/\\]transcript\.jsonl|Showing lines \d+-\d+ of \d+|The command exited with code -?\d+|Traceback \(most recent call last\):)',
    re.IGNORECASE,
)
_AP14_V2_TRANSCRIPT_RE = re.compile(r'(?:"step_index"\s*:|\b(?:PLANNER_RESPONSE|USER_INPUT|SYSTEM_SDK|TOOL_RESULT)\b)')
_AP15_BRIEF_ID_RE = re.compile(r"(?:\bIB-\d{8}-[A-Z0-9]{6,8}\b|#\s*Intent\s+Brief\b)", re.IGNORECASE)
_AP15_REGISTERED_BLOCK_RE = re.compile(r"(?:^|\n)\s*(?:#{1,4}\s*)?(?:parametri\s+registrati|registered\s+contacts)\s*:", re.IGNORECASE)


def _make_violation(code: str, severity: str, message: str, rule: str) -> Dict[str, str]:
    return {"code": code, "id": code, "severity": severity, "message": message, "msg": message, "rule": rule}


def _is_safe_host(host: str) -> bool:
    if not host or "\\" in host:
        return False
    try:
        parsed_host = urllib.parse.urlsplit(f"//{host}").hostname
    except ValueError:
        return False
    if not parsed_host:
        return False
    clean_host = parsed_host.rstrip(".").lower()
    if clean_host in ("127.0.0.1", "0.0.0.0", "::1"):
        return True
    return any(clean_host == d or clean_host.endswith("." + d) for d in _SAFE_DOMAINS) or clean_host.endswith((".example", ".test", ".invalid"))


def strip_zero_width_chars(text: str) -> str:
    """Rimuove caratteri zero-width e BOM invisibili dal testo."""
    return text.translate(_ZERO_WIDTH_TRANS) if text else ""


def _is_secret_like_val(val: str) -> bool:
    return any(c.isdigit() for c in val) or "_" in val or any(not c.isalnum() for c in val) or (any(c.islower() for c in val) and any(c.isupper() for c in val[1:]))


def redact_pii_deterministic(text: str) -> Tuple[str, int]:
    """Oscura deterministicamente DSN, secret, credenziali HTTP, email reali e telefoni."""
    if not text:
        return "", 0
    total = 0
    out = text
    if "PRIVATE KEY" in out:
        out, n = _PEM_KEY_RE.subn("[REDACTED_SECRET]", out)
        total += n
    if "://" in out:
        for pat in (_DSN_PASS_RE, _HTTP_CRED_RE):
            out, n = pat.subn("[REDACTED_SECRET]", out)
            total += n
    if "bearer" in out.lower():
        out, n = _BEARER_RE.subn("[REDACTED_SECRET]", out)
        total += n
    out, n = _SECRET_PREFIX_RE.subn("[REDACTED_SECRET]", out)
    total += n

    def _sub_kv_secret(m: re.Match[str]) -> str:
        nonlocal total
        prefix, sep, space, quote, val, end_q = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        if sep == ":" and not (bool(quote and end_q == quote) or _is_secret_like_val(val)):
            return m.group(0)
        total += 1
        return f"{prefix}{sep}{space}{quote}[REDACTED_SECRET]{end_q}"

    def _sub_email(m: re.Match[str]) -> str:
        nonlocal total
        if _is_safe_host(m.group(2)):
            return m.group(0)
        total += 1
        return "[REDACTED_EMAIL]"

    def _sub_phone(m: re.Match[str]) -> str:
        nonlocal total
        raw_num = m.group(2).strip()
        if _ISO_DATE_RE.fullmatch(raw_num) or not (7 <= sum(ch.isdigit() for ch in raw_num) <= 15):
            return m.group(0)
        total += 1
        return f"{m.group(1)}[REDACTED_PHONE]"

    out = _KV_SECRET_RE.sub(_sub_kv_secret, out)
    if "@" in out:
        out = _EMAIL_RE.sub(_sub_email, out)
    out = _PHONE_CTX_RE.sub(_sub_phone, out)
    return out, total


def _has_unguarded_live_endpoint(clean: str, strict_registered: bool) -> bool:
    if "://" not in clean:
        return False
    if _HTTP_CRED_RE.search(clean):
        return True
    for m_dsn in _DSN_ANY_RE.finditer(clean):
        auth = m_dsn.group(1)
        if "\\" in auth:
            return True
        if "@" in auth:
            userinfo, _, hostpart = auth.partition("@")
            if "@" in hostpart or any(ch in userinfo for ch in ("/", "\\", ".")):
                return True
        if not _is_safe_host(auth):
            return True
    for m_url in _HTTP_URL_RE.finditer(clean):
        host, path = m_url.group(1), m_url.group(2)
        if "@" in host:
            return True
        if not _is_safe_host(host) and (strict_registered or _LIVE_URL_HINT_RE.search(host + path)):
            return True
    return False
