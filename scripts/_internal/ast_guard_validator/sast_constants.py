"""Costanti TAS/SAST e pattern lessicali per SASTConstructChecker."""

from __future__ import annotations

import re
from typing import Set


TOK_PYTEST_CUR: str = "_".join(("PYTEST", "CURRENT", "TEST"))
TOK_NK_SANDBOX: str = "_".join(("NK", "SANDBOX"))
TOK_FIXTURE_FN: str = "_" + "_".join(("ensure", "sandbox", "benchmark", "fixture"))
TOK_EXT_PROJ: str = "_".join(("NK", "External", "Projects"))
ENV_VAR_NAMES_PATTERN: str = (
    "(?:"
    + "|".join(("TEMP", "TMP", "USERPROFILE", "APPDATA", "LOCALAPPDATA"))
    + ")"
)
LITERAL_ENV_PATH_RE = re.compile(
    "(?:"
    + chr(37)
    + ENV_VAR_NAMES_PATTERN
    + chr(37)
    + r"|\$env:"
    + ENV_VAR_NAMES_PATTERN
    + r"\b|\$\{env:"
    + ENV_VAR_NAMES_PATTERN
    + r"\})",
    re.IGNORECASE,
)
FRAME_ATTRS: Set[str] = {"f_back", "f_globals", "f_locals", "f_builtins", "f_code"}
MRO_EVASION_ATTRS: Set[str] = {
    "__subclasses__",
    "__globals__",
    "__mro__",
    "__bases__",
    "__base__",
}
DANGEROUS_MODULES: Set[str] = {
    "builtins",
    "__builtins__",
    "os",
    "posix",
    "nt",
    "subprocess",
    "pty",
    "ctypes",
    "shutil",
    "pickle",
    "marshal",
    "importlib",
    "inspect",
}
DANGEROUS_LOOKUP_SYMS: Set[str] = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "system",
    "popen",
    "__builtins__",
    "builtins",
    "__globals__",
    "__subclasses__",
    "__dict__",
    "getattr",
    "__getattribute__",
    "builtins.__getattribute__",
    "__builtins__.__getattribute__",
    "object.__getattribute__",
    "type.__getattribute__",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "vars",
    "windll",
}
MOCK_SYMBOLS: Set[str] = {
    "MagicMock",
    "AsyncMock",
    "NonCallableMock",
    "PropertyMock",
}
PATH_CTORS: Set[str] = {
    "Path",
    "PurePath",
    "PosixPath",
    "WindowsPath",
    "PurePosixPath",
    "PureWindowsPath",
}
SUBPROCESS_CALLS: Set[str] = {
    "run",
    "Popen",
    "call",
    "check_call",
    "check_output",
}
GRANT_SNAPSHOT_NAMES: Set[str] = {
    "grants",
    "snapshots",
    "grant_list",
    "snapshot_list",
    "grant_items",
    "snapshot_items",
    "bandi_grants",
}
SUSPICIOUS_HARDCODED_TOKENS: Set[str] = {
    "GOLDEN_FIXTURE_BYPASS",
    "ORACLE_BYPASS",
    "BENCHMARK_BYPASS",
    "MOCK_DB_RESULT",
}
