# -*- coding: utf-8 -*-
"""Costanti e regole regex pure-stdlib per il gate statico Frontend."""

from __future__ import annotations

import re
from typing import Set, Tuple

FRONTEND_EXTENSIONS: Set[str] = {".ts", ".tsx", ".js", ".jsx", ".css"}
_SKIP_DIRS: Set[str] = {"node_modules", ".next", "dist", "build", "__pycache__", ".git"}

_TS_BYPASS_COMMENT_RE = re.compile(r"@ts-(?:ignore|nocheck)\b")
_CSS_CUSTOM_PROP_RE = re.compile(r"--[a-zA-Z0-9_-]+\s*:")
_INLINE_HEX_RE = re.compile(
    r"(?:[:'\"\s])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})\b"
)

_REGEX_PREFIX_KEYWORDS: Set[str] = {
    "return",
    "throw",
    "case",
    "else",
    "do",
    "typeof",
    "void",
    "delete",
    "in",
    "instanceof",
    "new",
    "await",
    "yield",
    "of",
}

_JS_TS_RULES: Tuple[Tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "FE-XSS-SINK",
        "HIGH",
        re.compile(r"\bdangerouslySetInnerHTML\b|document\.write\s*\(|\.innerHTML\s*="),
        "Unsafe DOM XSS sink detected in frontend code.",
    ),
    (
        "FE-DYNAMIC-EXEC",
        "HIGH",
        re.compile(r"\beval\s*\(|\bnew\s+Function\s*\("),
        "Unsafe dynamic code execution sink detected in frontend code.",
    ),
    (
        "FE-TS-BYPASS",
        "MEDIUM",
        re.compile(r"\bas\s+any\b"),
        "TypeScript type-safety bypass ('as any') detected.",
    ),
)

_CSS_RULES: Tuple[Tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "FE-CSS-UNSAFE-URL",
        "HIGH",
        re.compile(r"url\(\s*['\"]?\s*javascript:|expression\s*\(", re.IGNORECASE),
        "Unsafe active script construct in CSS detected.",
    ),
)
