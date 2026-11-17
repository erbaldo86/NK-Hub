"""Estrazione target redirezione, flag output e archivi (re-export tokenizzazione)."""

from __future__ import annotations

import os
import re
from typing import List

from _internal.nk_hook_gate.constants import (
    _ARCHIVE_EXTRACT_RE,
    _CMD_C_WRAPPER_RE,
    _OUTPUT_FLAG_NAMES,
    _PROD_DIR_PREFIXES,
    _PROTECTED_FILE_EXTS,
    _PROTECTED_PROJECT_SEGMENTS,
    _PROTECTED_ROOT_FILENAMES,
    _PS_COMMAND_WRAPPER_RE,
    _strip_wrapping_quotes,
)
from _internal.nk_hook_gate.shell_tokenize import (
    _deobfuscate_ps_backticks,
    _extract_balanced_parens,
    _has_unquoted_ps_backtick_obfuscation,
    _norm_cmd_verb,
    _split_shell_segments,
    _split_top_level_args,
    _tokenize_shell_tokens,
    _unwrap_shell_subcommands,
)

_ONLY_MATCHING_O_VERBS = frozenset(("rg", "ripgrep", "grep", "egrep", "fgrep"))
_ARCHIVE_VERBS = frozenset(
    ("tar", "expand-archive", "unzip", "7z", "7za", "unpack_archive")
)
_ARCHIVE_CMD_SPLIT_RE = re.compile(r"([a-z0-9_.-]+)$", re.IGNORECASE)


def _extract_redirection_targets_single(cmd_str: str) -> List[str]:
    """Estrae i target effettivi dopo > o >> ignorando 2>&1, 1>&2, >&2 e operatori >=, =>, ->."""
    if ">" not in cmd_str:
        return []
    targets: List[str] = []
    in_single = False
    in_double = False
    idx = 0
    n = len(cmd_str)
    while idx < n:
        ch = cmd_str[idx]
        if in_single:
            if ch == "'":
                in_single = False
            idx += 1
            continue
        if in_double:
            if ch == "\\" and idx + 1 < n and cmd_str[idx + 1] in ('"', "\\"):
                idx += 2
                continue
            if ch == "`" and idx + 1 < n:
                idx += 2
                continue
            if ch == '"':
                in_double = False
            idx += 1
            continue
        if ch == "'":
            in_single = True
            idx += 1
            continue
        if ch == '"':
            in_double = True
            idx += 1
            continue
        if ch == ">":
            prev_ch = cmd_str[idx - 1] if idx > 0 else ""
            if prev_ch in ("-", "="):
                idx += 1
                continue
            op_end = idx + 2 if (idx + 1 < n and cmd_str[idx + 1] == ">") else idx + 1
            if op_end < n and cmd_str[op_end] == "=":
                idx = op_end + 1
                continue
            if op_end == idx + 1 and op_end < n and cmd_str[op_end] == "&":
                m_dup = re.match(r"^&(?:\d+|-)(?=$|[\s;|&)])", cmd_str[op_end:])
                if m_dup:
                    idx = op_end + len(m_dup.group(0))
                    continue
            j = op_end
            while j < n and cmd_str[j] in (" ", "\t"):
                j += 1
            if j >= n or cmd_str[j] in (";", "|", "&", "\n", "\r", ")", "<", ">"):
                targets.append("__empty_redirect__")
                idx = j
                continue
            tok_chars: List[str] = []
            q_char = ""
            while j < n:
                c = cmd_str[j]
                if q_char:
                    if (
                        q_char == '"'
                        and c == "\\"
                        and j + 1 < n
                        and cmd_str[j + 1] == '"'
                    ):
                        tok_chars.append(cmd_str[j + 1])
                        j += 2
                        continue
                    if c == q_char:
                        q_char = ""
                        j += 1
                        continue
                    tok_chars.append(c)
                    j += 1
                    continue
                if c in ("'", '"'):
                    q_char = c
                    j += 1
                    continue
                if c in (" ", "\t", ";", "|", "&", "\n", "\r", "(", ")", "<", ">"):
                    break
                tok_chars.append(c)
                j += 1
            targets.append("".join(tok_chars).strip() or "__empty_redirect__")
            idx = j
            continue
        idx += 1
    return targets


def _extract_redirection_targets(cmd_str: str) -> List[str]:
    """Raccoglie i target di redirezione dal comando principale e dai wrapper shell annidati."""
    targets = _extract_redirection_targets_single(cmd_str)
    for sub in _unwrap_shell_subcommands(cmd_str):
        targets.extend(_extract_redirection_targets_single(sub))
    return targets


def _looks_like_path_token(val: str) -> bool:
    """Verifica rapidamente se una stringa ricorda un percorso o nome file di progetto."""
    low = val.replace("\\", "/").strip().lower()
    if not low or " " in low and not (len(low) > 2 and low[1:3] == ":/"):
        if "/" not in low and "\\" not in val:
            return False
    if "/" in low or "\\" in val:
        return True
    if low.startswith(".staging") or low in _PROTECTED_ROOT_FILENAMES:
        return True
    _, ext = os.path.splitext(low)
    return ext in _PROTECTED_FILE_EXTS


def _extract_output_flag_targets_segment(seg: str) -> List[str]:
    """Estrae i target passati ai flag di output (--snapshot-out, --output, -o, -OutFile, ecc.)."""
    tokens = _tokenize_shell_tokens(seg)
    if not tokens:
        return []
    words = [u for _, u, _ in tokens]
    first_idx = 1 if len(words) > 1 and words[0] == "&" else 0
    v0 = _norm_cmd_verb(words[first_idx])
    is_pytest = v0 == "pytest" or (
        v0 in ("python", "python3", "py")
        and "-m" in words[first_idx + 1 : first_idx + 4]
        and "pytest" in [os.path.basename(w).lower() for w in words[first_idx + 1 : first_idx + 5]]
    )
    out: List[str] = []
    i = first_idx + 1
    n = len(words)
    while i < n:
        tok = words[i]
        low = tok.lower()
        eq_val = ""
        flag_key = low
        for sep in ("=", ":"):
            if sep in low and not (len(low) >= 2 and low[1] == ":" and sep == ":"):
                flag_key, eq_val = low.split(sep, 1)
                eq_val = tok.split(sep, 1)[1]
                break

        if eq_val and flag_key in _OUTPUT_FLAG_NAMES:
            out.append(_strip_wrapping_quotes(eq_val) or "__empty_redirect__")
            i += 1
            continue

        if low in _OUTPUT_FLAG_NAMES:
            if i + 1 < n and words[i + 1].strip():
                out.append(_strip_wrapping_quotes(words[i + 1]))
                i += 2
            else:
                out.append("__empty_redirect__")
                i += 1
            continue

        if low == "-o":
            if v0 in _ONLY_MATCHING_O_VERBS:
                i += 1
                continue
            if is_pytest:
                if i + 1 < n:
                    nxt = _strip_wrapping_quotes(words[i + 1])
                    rhs = nxt.split("=", 1)[1] if "=" in nxt else nxt
                    if _looks_like_path_token(rhs):
                        out.append(rhs)
                    i += 2
                else:
                    i += 1
                continue
            if i + 1 < n and words[i + 1].strip():
                out.append(_strip_wrapping_quotes(words[i + 1]))
                i += 2
            else:
                out.append("__empty_redirect__")
                i += 1
            continue

        if (
            low.startswith("-o")
            and len(low) > 2
            and v0 not in _ONLY_MATCHING_O_VERBS
            and not is_pytest
            and (v0 in ("7z", "7za") or "/" in tok[2:] or "\\" in tok[2:])
        ):
            out.append(_strip_wrapping_quotes(tok[2:]))
            i += 1
            continue

        i += 1
    return out


def _extract_output_flag_targets(cmd_str: str) -> List[str]:
    """Raccoglie i target dei flag di output da tutti i segmenti e subcomandi wrapper."""
    targets: List[str] = []
    for raw_sub in (cmd_str, _deobfuscate_ps_backticks(cmd_str), *_unwrap_shell_subcommands(cmd_str)):
        for seg in _split_shell_segments(raw_sub):
            targets.extend(_extract_output_flag_targets_segment(seg))
    return targets


def _extract_archive_targets_segment(seg: str) -> List[str]:
    """Estrae la directory destinazione per comandi di estrazione archivio (o '.' se omessa)."""
    if not _ARCHIVE_EXTRACT_RE.search(seg):
        return []
    targets: List[str] = []
    if "unpack_archive(" in seg.lower():
        for m in re.finditer(r"\bunpack_archive\s*\(", seg, re.IGNORECASE):
            bal = _extract_balanced_parens(seg, m.end() - 1)
            if bal is not None:
                p_args = _split_top_level_args(bal[0].strip())
                dest = ""
                for idx_a, a in enumerate(p_args):
                    if re.match(r"^extract_dir\s*=", a, re.IGNORECASE):
                        dest = _strip_wrapping_quotes(a.split("=", 1)[1])
                        break
                    if idx_a == 1 and "=" not in a:
                        dest = _strip_wrapping_quotes(a)
                targets.append(dest or ".")
        if targets:
            return targets

    tokens = _tokenize_shell_tokens(seg)
    if not tokens:
        return ["."]
    words = [u for _, u, _ in tokens]
    first_idx = 1 if len(words) > 1 and words[0] == "&" else 0
    v0 = _norm_cmd_verb(words[first_idx])
    if v0 not in _ARCHIVE_VERBS:
        return ["."]

    i = first_idx + 1
    n = len(words)
    pos_args: List[str] = []
    while i < n:
        w = words[i]
        wl = w.lower()
        if wl in ("-c", "--directory", "-d", "-destinationpath", "-destination"):
            if i + 1 < n:
                targets.append(_strip_wrapping_quotes(words[i + 1]) or ".")
                i += 2
                continue
        if wl.startswith(("--directory=", "-destinationpath:", "-destinationpath=", "-destination:", "-destination=")):
            val = w.split("=", 1)[1] if "=" in w else w.split(":", 1)[1]
            targets.append(_strip_wrapping_quotes(val) or ".")
            i += 1
            continue
        if len(wl) > 2 and (wl.startswith("-c") or wl.startswith("-d") or wl.startswith("-o")):
            if v0 in ("7z", "7za") and wl.startswith("-o"):
                targets.append(_strip_wrapping_quotes(w[2:]) or ".")
                i += 1
                continue
            if v0 == "tar" and wl.startswith("-c") and not wl.startswith("--"):
                targets.append(_strip_wrapping_quotes(w[2:]) or ".")
                i += 1
                continue
            if v0 == "unzip" and wl.startswith("-d"):
                targets.append(_strip_wrapping_quotes(w[2:]) or ".")
                i += 1
                continue
        if v0 in ("7z", "7za") and wl == "-o" and i + 1 < n:
            targets.append(_strip_wrapping_quotes(words[i + 1]) or ".")
            i += 2
            continue
        if not wl.startswith("-"):
            pos_args.append(_strip_wrapping_quotes(w))
        i += 1

    if v0 == "expand-archive" and not targets and len(pos_args) >= 2:
        targets.append(pos_args[1] or ".")
    if not targets:
        targets.append(".")
    return targets


def _extract_archive_targets(cmd_str: str) -> List[str]:
    """Raccoglie tutti i target di estrazione archivio nel comando e nei wrapper."""
    targets: List[str] = []
    for raw_sub in (cmd_str, _deobfuscate_ps_backticks(cmd_str), *_unwrap_shell_subcommands(cmd_str)):
        for seg in _split_shell_segments(raw_sub):
            targets.extend(_extract_archive_targets_segment(seg))
    return targets


__all__ = [
    "_ARCHIVE_CMD_SPLIT_RE",
    "_ARCHIVE_VERBS",
    "_ONLY_MATCHING_O_VERBS",
    "_deobfuscate_ps_backticks",
    "_extract_archive_targets",
    "_extract_archive_targets_segment",
    "_extract_balanced_parens",
    "_extract_output_flag_targets",
    "_extract_output_flag_targets_segment",
    "_extract_redirection_targets",
    "_extract_redirection_targets_single",
    "_has_unquoted_ps_backtick_obfuscation",
    "_looks_like_path_token",
    "_norm_cmd_verb",
    "_split_shell_segments",
    "_split_top_level_args",
    "_tokenize_shell_tokens",
    "_unwrap_shell_subcommands",
]
