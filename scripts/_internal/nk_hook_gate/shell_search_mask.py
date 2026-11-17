"""Mascheramento pattern read-only (rg, grep, findstr, Select-String, git)."""

from __future__ import annotations

from typing import Dict, Set

from _internal.nk_hook_gate.constants import _DESTRUCTIVE_GIT_RE
from _internal.nk_hook_gate.shell_ast_paths import _PS_FLAGS_WITH_ARG
from _internal.nk_hook_gate.shell_parser import (
    _extract_redirection_targets_single,
    _norm_cmd_verb,
    _split_shell_segments,
    _tokenize_shell_tokens,
)
from _internal.nk_hook_gate.shell_redaction import _scan_quotes_clean

_READONLY_SEARCH_VERBS = frozenset(
    ("rg", "ripgrep", "grep", "egrep", "fgrep", "ag", "findstr", "select-string", "sls")
)
_READONLY_SEARCH_VAL_FLAGS = frozenset(
    (
        "-f", "--file", "-path", "-literalpath", "-g", "--glob", "-t", "--type",
        "--type-not", "-a", "--after-context", "-b", "--before-context", "-c",
        "--context", "-m", "--max-count", "--max-depth", "-j", "--threads",
        "--encoding", "-e-file", "--color", "-exclude", "-include", "-context",
        "-encoding", "--sort", "--sortr", "--max-columns", "--iglob",
    )
)
_GIT_SAFE_INSPECT_SUBS = frozenset(("grep", "log", "show", "diff", "status", "ls-files"))
_GIT_SAFE_GLOBAL_VAL_FLAGS = frozenset(("--git-dir", "--work-tree"))


def _strip_readonly_search_patterns(subcmd: str) -> str:
    """Maschera i soli pattern in un segmento read-only singolo (rg/grep/findstr/Select-String/git)."""
    if not subcmd or not subcmd.strip():
        return subcmd
    if (
        "`" in subcmd
        or "$(" in subcmd
        or "${" in subcmd
        or "<(" in subcmd
        or ">(" in subcmd
        or "\n" in subcmd
        or "\r" in subcmd
    ):
        return subcmd
    if _DESTRUCTIVE_GIT_RE.search(subcmd):
        return subcmd
    if _extract_redirection_targets_single(subcmd):
        return subcmd
    if not _scan_quotes_clean(subcmd, allow_backslash_escape=True):
        return subcmd
    if not _scan_quotes_clean(subcmd, allow_backslash_escape=False):
        return subcmd

    tokens = _tokenize_shell_tokens(subcmd)
    if not tokens:
        return subcmd
    _, unq0, _ = tokens[0]
    if unq0.startswith(("$", "&", ".")):
        return subcmd
    v0 = _norm_cmd_verb(unq0)

    mask_indices: Set[int] = set()
    pref_masks: Dict[int, str] = {}

    if v0 in _READONLY_SEARCH_VERBS:
        for _, unq_t, _ in tokens[1:]:
            tl = unq_t.lower()
            if tl in ("--pre", "--hostname-bin") or tl.startswith(("--pre=", "--hostname-bin=")):
                return subcmd
        i = 1
        n = len(tokens)
        has_explicit_pat = False
        pos_masked = False
        after_dd = False
        while i < n:
            _, unq_t, _ = tokens[i]
            tl = unq_t.lower()
            if not after_dd and unq_t == "--":
                after_dd = True
                i += 1
                continue
            if not after_dd and tl in ("-e", "--regexp", "-pattern"):
                if i + 1 < n:
                    mask_indices.add(i + 1)
                    has_explicit_pat = True
                    i += 2
                    continue
            if not after_dd and tl.startswith(("--regexp=", "-pattern=", "-pattern:", "-e=")):
                sep = "=" if "=" in unq_t else ":"
                pref_masks[i] = unq_t.split(sep, 1)[0] + sep + "__SAFE_SEARCH_PAT__"
                has_explicit_pat = True
                i += 1
                continue
            if not after_dd and v0 == "findstr" and tl.startswith("/c:"):
                pref_masks[i] = '/c:"__SAFE_SEARCH_PAT__"'
                has_explicit_pat = True
                i += 1
                continue
            if not after_dd and v0 == "findstr" and tl == "/c":
                if i + 1 < n:
                    mask_indices.add(i + 1)
                    has_explicit_pat = True
                    i += 2
                    continue
            if not after_dd and tl in _READONLY_SEARCH_VAL_FLAGS:
                i += 2
                continue
            if not after_dd and (tl.startswith("-") or (v0 == "findstr" and len(tl) == 2 and tl.startswith("/"))):
                i += 1
                continue
            if not has_explicit_pat and not pos_masked:
                mask_indices.add(i)
                pos_masked = True
            i += 1
    elif v0 == "git":
        i = 1
        n = len(tokens)
        git_sub = ""
        while i < n:
            _, unq_t, _ = tokens[i]
            tl = unq_t.lower()
            if tl == "-c" and i + 1 < n:
                return subcmd
            if tl in ("--exec-path", "--upload-pack") or tl.startswith(("--exec-path=", "--upload-pack=")):
                return subcmd
            if tl in _GIT_SAFE_GLOBAL_VAL_FLAGS or tl == "-c":
                i += 2
                continue
            if unq_t == "-C":
                i += 2
                continue
            if tl.startswith(("-c=", "-C", "--git-dir=", "--work-tree=")):
                i += 1
                continue
            if tl.startswith("-"):
                i += 1
                continue
            git_sub = tl
            i += 1
            break
        if git_sub not in _GIT_SAFE_INSPECT_SUBS:
            return subcmd
        after_dd = False
        has_explicit = False
        pos_masked = False
        while i < n:
            _, unq_t, _ = tokens[i]
            tl = unq_t.lower()
            if not after_dd and unq_t == "--":
                after_dd = True
                i += 1
                continue
            if not after_dd and git_sub in ("log", "diff", "show"):
                if tl in ("-s", "-g", "--grep") and i + 1 < n:
                    mask_indices.add(i + 1)
                    i += 2
                    continue
                if tl.startswith("--grep=") or (len(unq_t) > 2 and unq_t[:2] in ("-S", "-G")):
                    pref_masks[i] = (
                        "--grep=__SAFE_SEARCH_PAT__"
                        if tl.startswith("--grep=")
                        else unq_t[:2] + "__SAFE_SEARCH_PAT__"
                    )
                    i += 1
                    continue
            if not after_dd and git_sub == "grep":
                if tl in ("-e", "--regexp") and i + 1 < n:
                    mask_indices.add(i + 1)
                    has_explicit = True
                    i += 2
                    continue
                if tl.startswith(("--regexp=", "-e=")) or (len(unq_t) > 2 and tl.startswith("-e")):
                    pref_masks[i] = "-e__SAFE_SEARCH_PAT__"
                    has_explicit = True
                    i += 1
                    continue
                if not tl.startswith("-") and not has_explicit and not pos_masked:
                    mask_indices.add(i)
                    pos_masked = True
            i += 1
    elif v0 in ("powershell", "pwsh", "cmd"):
        payload_idx: int | None = None
        i = 1
        n = len(tokens)
        while i < n:
            _, unq_t, _ = tokens[i]
            tl = unq_t.lower()
            if v0 == "cmd" and tl == "/c":
                payload_idx = i + 1
                break
            if v0 in ("powershell", "pwsh") and tl in ("-c", "-command"):
                payload_idx = i + 1
                break
            if v0 in ("powershell", "pwsh") and tl in _PS_FLAGS_WITH_ARG:
                i += 2
                continue
            if tl.startswith("-") or (v0 == "cmd" and tl.startswith("/")):
                i += 1
                continue
            return subcmd
        if payload_idx is None or payload_idx >= n:
            return subcmd
        inner_cmd = (
            tokens[payload_idx][1]
            if payload_idx == n - 1
            else " ".join(raw for raw, _, _ in tokens[payload_idx:])
        )
        inner_segs = _split_shell_segments(inner_cmd)
        if len(inner_segs) != 1:
            return subcmd
        masked_inner = _strip_readonly_search_patterns(inner_segs[0])
        if masked_inner == inner_segs[0]:
            return subcmd
        prefix = " ".join(raw for raw, _, _ in tokens[:payload_idx])
        return f"{prefix} {masked_inner}".strip()
    else:
        return subcmd

    if not mask_indices and not pref_masks:
        return subcmd
    return " ".join(
        pref_masks[idx_t]
        if idx_t in pref_masks
        else ("__SAFE_SEARCH_PAT__" if idx_t in mask_indices else raw_t)
        for idx_t, (raw_t, _, _) in enumerate(tokens)
    )
