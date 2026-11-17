"""Pattern linguistici e lessico per l'analisi dell'intento di scrittura vs lettura."""

from __future__ import annotations

import re
from typing import Set, Tuple

from _internal.vibe_sprint_router.constants_core import _READ_ONLY_ROLES


_NEGATION_TOKENS: Set[str] = {
    "non",
    "senza",
    "né",
    "ne",
    "mai",
    "vietato",
    "evita",
    "evitando",
    "nessuna",
    "nessun",
    "nessuno",
    "niente",
    "nulla",
}
_ADVERSATIVE_TOKENS: Set[str] = {
    "ma",
    "però",
    "pero",
    "bensì",
    "bensi",
    "invece",
}
_ITALIAN_NOUN_DETERMINERS: Set[str] = {
    "il",
    "lo",
    "la",
    "i",
    "gli",
    "le",
    "l",
    "un",
    "uno",
    "una",
    "del",
    "dello",
    "della",
    "dei",
    "degli",
    "delle",
    "dell",
    "al",
    "allo",
    "alla",
    "ai",
    "agli",
    "alle",
    "all",
    "dal",
    "dallo",
    "dalla",
    "dai",
    "dagli",
    "dalle",
    "dall",
    "nel",
    "nello",
    "nella",
    "nei",
    "negli",
    "nelle",
    "nell",
    "sul",
    "sullo",
    "sulla",
    "sui",
    "sugli",
    "sulle",
    "sull",
    "questo",
    "questa",
    "questi",
    "queste",
    "quello",
    "quella",
    "quelli",
    "quelle",
    "quel",
    "ogni",
    "qualche",
    "tale",
    "tali",
    "eventuale",
    "eventuali",
    "ultima",
    "ultimo",
}
_LIGHT_EXEC_VERBS: Set[str] = {
    "fai",
    "fare",
    "applica",
    "applicare",
    "apporta",
    "apportare",
    "effettua",
    "effettuare",
}
_ANALYTICAL_AUDIT_HEADS: Set[str] = {
    "analizza",
    "analizzare",
    "analisi",
    "audit",
    "verifica",
    "verificare",
    "controlla",
    "controllare",
    "controllo",
    "valuta",
    "valutare",
    "valutazione",
    "ispeziona",
    "ispezionare",
    "ispezione",
    "esamina",
    "esaminare",
    "individua",
    "individuare",
    "rileva",
    "rilevare",
    "trova",
    "trovare",
    "cerca",
    "cercare",
    "review",
}
_SUBORDINATE_WH_TOKENS: Set[str] = {
    "perché",
    "perche",
    "dove",
    "come",
    "quando",
    "cosa",
    "chi",
    "quale",
    "quali",
    "quanto",
    "quanti",
    "se",
    "mentre",
}
_COORDINATED_IMPERATIVE_PREFIX_TOKENS: Set[str] = {
    "e",
    "ed",
    "poi",
    "inoltre",
    "quindi",
    "ora",
    "adesso",
    "subito",
    "dopo",
}
_WORD_TOKEN_RE = re.compile(r"[a-z0-9_àèéìòù]+")
_EXPLANATORY_CLAUSE_START_RE = re.compile(
    r"^(?:spiega|dimmi|illustra|descrivi|perch[eé]|dove|come\s+funziona|come\s+avviene|cosa\s+fa|cosa\s+succede|quali\b|quale\b|chi\b|quando\b)",
    re.IGNORECASE,
)
_DOS_DEL_ARG_TAIL = (
    r"(?:(?:/[qfsap]\b\s*)+"
    r"|[\"']?[a-zA-Z]:\\[^\s\"']+"
    r"|[\"']?(?:\.\.?\\)?[\w\-.]*\\[\w\-.\\*]+"
    r"|[\"']?[\w\-*]+\.[a-zA-Z0-9*]{1,8}(?=\s|$|[;&|\"']))"
)
_DOS_DEL_AT_START_RE = re.compile(rf"^del\s+{_DOS_DEL_ARG_TAIL}", re.IGNORECASE)
_DOS_DEL_AFTER_SEP_RE = re.compile(
    rf"(?:[;&|`\n]|\bcmd(?:\.exe)?\s+/c\s+)\s*del\s+{_DOS_DEL_ARG_TAIL}",
    re.IGNORECASE,
)
_DESTRUCTIVE_SHELL_CMD_RE = re.compile(
    r"(?:\brm\s+-[rf]{1,2}\b|\bremove-item\b|\brmdir\s+/s\b|\bdrop\s+(?:table|database)\b|\bdelete\s+from\b)",
    re.IGNORECASE,
)
_VERB_CONJ_TAIL = r"(?:re|rò|rai|rà|remo|rete|ranno|ò|ai|à|emo|ete|anno|iamo|iate|ino|ano|lo|la|li|le)?\b"
_WRITE_ROOT_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("implement", ("implementa", "implementi", "implementer")),
    ("svilupp", ("sviluppa", "sviluppi", "svilupper")),
    ("refactor", ("refactoring", "refactor")),
    ("modific", ("modifica", "modifichi", "modificher")),
    ("forgia", ("forgia",)),
    ("crea", ("crea",)),
    ("crei", ("crei",)),
    ("creer", ("creer",)),
    ("sincronizz", ("sincronizza", "sincronizzi")),
    ("alline", ("allinea", "allinei")),
    ("progett", ("progetta", "progetti")),
    ("aggiorn", ("aggiorna", "aggiorni", "aggiorner")),
    ("aggiung", ("aggiungi", "aggiunga", "aggiunger")),
    ("scriv", ("scrivi", "scriva", "scriver")),
    ("corregg", ("correggi", "corregga", "corregger")),
    ("sistem", ("sistema", "sistemi", "sistemer")),
    ("cancell", ("cancella",)),
    ("elimin", ("elimina",)),
    ("rimuov", ("rimuovi", "rimuov")),
    ("sovrascriv", ("sovrascrivi", "sovrascriv")),
    ("accorp", ("accorpa", "accorpi", "accorper")),
    ("aggiust", ("aggiusta", "aggiusti", "aggiuster")),
    ("modernizz", ("modernizza", "modernizzi")),
    ("snell", ("snellisci", "snellisc")),
    ("riduc", ("riduci", "riduca", "ridurr")),
    ("fix", ("fix", "fixa", "fixi")),
    ("spost", ("sposta", "sposti", "sposter")),
    ("rinomin", ("rinomina", "rinomini", "rinominer")),
    ("rifattorizz", ("rifattorizza", "rifattorizzi")),
    ("decompon", ("decomponi", "decomponga")),
    ("certific", ("certifica", "certifichi")),
)
_WRITE_ROOT_PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = tuple(
    (
        root,
        re.compile(
            rf"\b(?:{'|'.join(re.escape(st) for st in stems)}){_VERB_CONJ_TAIL}"
        ),
    )
    for root, stems in _WRITE_ROOT_GROUPS
) + (
    (
        "ottimizz",
        re.compile(
            rf"\b(?:ottimizza|ottimizzi|ottimizzer){_VERB_CONJ_TAIL}"
            r"(?!\s+con\s+analisi\s+(?:approfondita|multi-livello)\b)"
        ),
    ),
)
_FAST_NOUN_DET_SUFFIXES: Tuple[str, ...] = (
    " il ",
    " lo ",
    " la ",
    " i ",
    " gli ",
    " le ",
    " l'",
    " un ",
    " uno ",
    " una ",
    " del ",
    " dello ",
    " della ",
    " dei ",
    " degli ",
    " delle ",
    " dell'",
    " al ",
    " dal ",
    " nel ",
    " sul ",
)
_ROLE_CONFLICT_WRITE_RE = re.compile(
    r"(applica(?:re)? la soluzione|crea un test|salva tutti i risultati|src_app/)",
    re.IGNORECASE,
)
_SINGLE_OPERA_RE = re.compile(r"Opera come\s+([^\n\.]+)", re.IGNORECASE)
_READ_ONLY_ROLES_LOWER: Tuple[Tuple[str, str], ...] = tuple(
    (r, r.lower()) for r in _READ_ONLY_ROLES
)
