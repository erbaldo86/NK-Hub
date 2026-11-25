# -*- coding: utf-8 -*-
"""
Suite di test unitari Zero-Mock per Static AST Guard Validator, Quality-Diff, Frontend Gate e Guardia GT-14.
Modulo: tests/test_ast_guard_validator.py.
Valida purezza sintattica, firme, scope, SAST, re-export, quality-diff e frontend lexer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Iterable

import pytest

try:
    from conftest import WORKSPACE_ROOT, call_script_main_captured, load_nk_script_module
except ImportError:
    from tests.conftest import WORKSPACE_ROOT, call_script_main_captured, load_nk_script_module

_agv_mod = load_nk_script_module("ast_guard_validator")
ASTGuardValidator = _agv_mod.ASTGuardValidator
ViolationType = _agv_mod.ViolationType

from _internal.ast_guard_validator import (  # noqa: E402
    frontend_static_checker as fe_chk,
    models as agv_models,
    quality_diff_checker as qd_chk,
    reexports as reexp_mod,
    signature_collector as sig_mod,
    validator_helpers as vhelp_mod,
)

_CLEAN_PRE = """
from typing import List

def calculate_sum(items: List[int], multiplier: int = 1) -> int:
    return sum(items) * multiplier
"""


def _assert_sast_blocked(snippets: Iterable[str], *, target_file: str = "<target>") -> None:
    for snippet in snippets:
        rep = ASTGuardValidator.validate_code_edit("", snippet, target_file=target_file)
        assert rep.is_valid is False, f"Expected SAST block for: {snippet}"
        assert any(v.violation_type == ViolationType.SAST_VIOLATION for v in rep.violations), snippet


@dataclass
class _CatalogItemSample:
    name: str
    score: int


def _assert_ast_guard_c_rules_and_types() -> None:
    assert ASTGuardValidator.validate_code_edit("def compute(a: int, b: int) -> int:\n    return a + b\n", "def compute(a: int, b: int = 10) -> int:\n    return a + b\n").is_valid
    assert ASTGuardValidator.validate_code_edit("def fetch(url: str) -> str:\n    return url\n", "def fetch(url: str, *, timeout: float = 5.0) -> str:\n    return url\n").is_valid
    rep_c3_bad = ASTGuardValidator.validate_code_edit("def fetch(url: str) -> str:\n    return url\n", "def fetch(url: str, *, timeout: float) -> str:\n    return url\n")
    assert (rep_c3_bad.is_valid, any(v.violation_type == ViolationType.SIGNATURE_MUTATION for v in rep_c3_bad.violations)) == (False, True)
    assert ASTGuardValidator.validate_code_edit("def _internal_helper(x: int) -> int:\n    return x + 1\n\ndef public_api(x: int) -> int:\n    return x + 1\n", "def public_api(x: int) -> int:\n    return x + 1\n").is_valid
    rep_dunder = ASTGuardValidator.validate_code_edit("class Box:\n    def __init__(self, v: int) -> None:\n        self.v = v\n", "class Box:\n    pass\n")
    assert (rep_dunder.is_valid, any(v.violation_type == ViolationType.UNAUTHORIZED_DELETION for v in rep_dunder.violations)) == (False, True)
    assert ASTGuardValidator.validate_code_edit(
        "from typing import Optional, List\ndef parse(tag: Optional[str], items: List[int]) -> Optional[int]:\n    return len(items) if tag else None\n",
        "from typing import Union\ndef parse(tag: str | None, items: list[int]) -> Union[int, None]:\n    return len(items) if tag else None\n",
    ).is_valid
    rep_nested = ASTGuardValidator.validate_code_edit(
        "", "def outer() -> int:\n    def inner() -> int:\n        secret_inner = 42\n        return secret_inner\n    return secret_inner\n",
    )
    assert (rep_nested.is_valid, any(v.violation_type == ViolationType.UNDEFINED_NAME and v.symbol_name == "secret_inner" for v in rep_nested.violations)) == (False, True)


def _assert_sig_collector_and_type_norm() -> None:
    col_src = (
        "import a.b as c\na, *b = [1, 2]\ntyped_g: int = 3\nfor loop_v in [1]: pass\nasync def top_af(): pass\n"
        "with ctx() as with_v: pass\ntry: pass\nexcept Exception as exc_v: pass\nclass Box[T]:\n"
        "    @property\n    def x(self): return 1\n    @x.getter\n    def x(self): return 2\n"
        "    @x.setter\n    def x(self, v): pass\n    @x.deleter\n    def x(self): pass\n"
        "def f(p: int, /, *va: int, **kw: str) -> None:\n    pass\n"
    )
    col = sig_mod.SignatureCollector()
    col.visit(ast.parse(col_src))
    assert {"Box.x", "Box.x[getter]", "Box.x[setter]", "Box.x[deleter]", "f"}.issubset(col.signatures)
    assert {"T", "c", "a", "b", "typed_g", "loop_v", "with_v", "exc_v"}.issubset(col.defined_globals)
    norms = (
        agv_models._normalize_type_annotation("NoneType"), agv_models._normalize_type_annotation('"Optional[int]"'),
        agv_models._normalize_type_annotation('"[bad"'), agv_models._normalize_type_annotation("typing.List[int]"),
        agv_models._normalize_type_annotation("Union[int, str, None]"), agv_models._normalize_type_annotation("Optional[Union[int, str]]"),
        agv_models._normalize_type_annotation("tuple[int, str]"), agv_models._normalize_type_annotation(""),
        agv_models._normalize_type_annotation("   "), agv_models._normalize_type_annotation(None),
        agv_models._normalize_type_annotation("[broken"),
    )
    assert norms == ("None", "int | None", "'[bad'", "list[int]", "int | str | None", "int | str | None", "tuple[int, str]", "", "", None, "[broken")


@pytest.mark.fast
def test_ast_guard_syntactic_auditors_signature_and_c_rules() -> None:
    """Valida sintassi, permessi read-only Auditor GT-14, firme, C2-C6, SignatureCollector e normalizer."""
    rep_syn = ASTGuardValidator.validate_code_edit(_CLEAN_PRE, "def calculate_sum(items: List[int]:\n    return 42")
    assert (rep_syn.is_valid, any(v.violation_type == ViolationType.SYNTAX_ERROR for v in rep_syn.violations)) == (False, True)

    for skill_name in ("NK-Ideator", "NK-Bug-Diagnostic-Engine", "NK-Security-Auditor", "NK-Dynamic-Sandbox-StressTester", "NK-Oracle-Evaluator"):
        skill_md = WORKSPACE_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
        assert skill_md.is_file()
        frontmatter = skill_md.read_text(encoding="utf-8").split("---")[1]
        assert ("write_to_file" in frontmatter, "enable_write_tools: true" in frontmatter) == (False, False)

    rep_a = ASTGuardValidator.validate_code_edit(_CLEAN_PRE, "from typing import List\n\ndef calculate_sum(items: List[int]) -> int:\n    return sum(items)\n")
    assert (rep_a.is_valid, any(v.violation_type == ViolationType.SIGNATURE_MUTATION for v in rep_a.violations)) == (False, True)
    rep_b = ASTGuardValidator.validate_code_edit(_CLEAN_PRE, "from typing import List\n\ndef calculate_sum(items: List[int], multiplier: int = 1) -> float:\n    return float(sum(items) * multiplier)\n")
    assert (rep_b.is_valid, any(v.violation_type == ViolationType.TYPE_MISMATCH for v in rep_b.violations)) == (False, True)
    _assert_ast_guard_c_rules_and_types()
    _assert_sig_collector_and_type_norm()


def _assert_scope_async_and_match_variants() -> None:
    valid_complex = (
        "class Box:\n    def __init__(self, v: int) -> None: self.v = v\n"
        "async def run_async(stream, ctx_mgr, mapping, obj):\n"
        "    a, b = 1, 2; del (a, b); c = [10]; del c[0]; obj.v += 1\n"
        "    fn = lambda *args, k=5, **kw: (args, k, kw)\n"
        "    dcomp = {str(i): i for i in range(2)}; scomp = {i for i in range(2)}; gcomp = sum(i for i in range(2))\n"
        "    async for item in stream: pass\n    async with ctx_mgr as handle: pass\n"
        "    match mapping:\n        case {'k': val, **rest_map}: return (val, rest_map, fn, dcomp, scomp, gcomp, handle)\n"
        "        case Box(v=1 | 2): return 2\n        case _: return 0\n"
    )
    assert ASTGuardValidator.validate_code_edit("", valid_complex).is_valid
    for bad_s in ("def f():\n    del a\n    return a\n", "def f():\n    x += 1\n    x = 2\n", "def f():\n    y += 1\n", "def f():\n    fn = lambda bad_arg=missing_def: bad_arg\n    return fn\n", "type BadVec[T] = MissingBase[T]\n"):
        assert ASTGuardValidator.validate_code_edit("", bad_s).is_valid is False
    assert ASTGuardValidator.validate_code_edit("", "def f(rows):\n    tot = 1\n    del tot\n    res = [tot := r for r in rows]\n    return (tot, res)\n").is_valid


@pytest.mark.fast
def test_ast_guard_scope_legb_walrus_and_async_variants() -> None:
    """Valida scope unbound, Match/PEP695/walrus, WP-R1 LEGB leak, C7 grants e Async/Delete/AugAssign."""
    unbound_post = "from typing import List\n\ndef calculate_sum(items: List[int], multiplier: int = 1) -> int:\n    return sum(items) * multiplier + undefined_external_val\n"
    rep = ASTGuardValidator.validate_code_edit(_CLEAN_PRE, unbound_post)
    assert (rep.is_valid, any(v.violation_type == ViolationType.UNDEFINED_NAME for v in rep.violations)) == (False, True)
    assert ASTGuardValidator.validate_code_edit("", "@undefined_decorator\ndef foo(): pass\n").is_valid is False
    assert ASTGuardValidator.validate_code_edit("", "def bar(val=undefined_default): pass\n").is_valid is False

    pep634_code = "def process_command(command):\n    match command:\n        case {'type': 'write', 'data': payload}: return payload\n        case [first, *rest]: return first\n        case _: return None\n"
    pep695_code = "type Vector[T] = list[T]\ndef identity[T](val: T) -> T:\n    return val\n"
    assert (
        ASTGuardValidator.validate_code_edit(pep634_code, pep634_code).is_valid,
        ASTGuardValidator.validate_code_edit(pep695_code, pep695_code).is_valid,
        ASTGuardValidator.validate_code_edit("", "def process_data(raw_items: list[str]) -> list[int]:\n    return [n for item in raw_items if (n := len(item)) > 3]\n").is_valid,
    ) == (True, True, True)

    rep_c7 = ASTGuardValidator.validate_code_edit("", "def has_many_permissions(user_grants: list) -> bool:\n    return len(user_grants) >= 12\n", target_file="src_app/auth_service.py")
    assert rep_c7.is_valid, rep_c7.violations
    assert ASTGuardValidator.validate_code_edit("", "def f():\n    items = [y := x + 1 for x in range(3)]\n    return y + len(items)\n").is_valid
    assert ASTGuardValidator.validate_code_edit("", "def outer():\n    def inner():\n        return (z_local := 1)\n    return z_local\n").is_valid is False

    for bad_ub, sym in (("def f():\n    y = x + 1\n    x = 2\n    return y\n", "x"), ("G_VAL = 10\ndef f():\n    y = G_VAL + 1\n    G_VAL = 2\n    return y\n", "G_VAL"), ("class Box:\n    secret = 42\n    def reveal(self) -> int:\n        return secret\n", "secret")):
        r_ub = ASTGuardValidator.validate_code_edit("", bad_ub)
        assert (r_ub.is_valid, any(v.violation_type == ViolationType.UNDEFINED_NAME and v.symbol_name == sym for v in r_ub.violations)) == (False, True)

    assert ASTGuardValidator.validate_code_edit("", "class Table:\n    ITEMS = [1, 2, 3]\n    DOUBLED = [x * 2 for x in ITEMS]\n").is_valid
    assert ASTGuardValidator.validate_code_edit("", "def outer():\n    def inner():\n        return late_v\n    late_v = 9\n    return inner()\n").is_valid
    _assert_scope_async_and_match_variants()


@pytest.mark.fast
def test_ast_guard_sast_evasion_aliases_and_yaml_matrix() -> None:
    """Valida evasioni SAST, alias CRIT-05, self-validator, SQLi, yaml/ctypes/gaming e missing branches."""
    t_mock, t_umock = "Magic" + "Mock", "unittest." + "mock"
    t_pytest = "PYTEST_" + "CURRENT_TEST"

    rep_yml = ASTGuardValidator.validate_code_edit("", "from yaml import load\ndef parse_y(d: str):\n    return load(d)\n")
    assert rep_yml.is_valid is False and any(v.symbol_name == "yaml.load" for v in rep_yml.violations)
    assert ASTGuardValidator.validate_code_edit("", "import yaml\ndef parse_y(d: str):\n    return yaml.load(d, Loader=yaml.SafeLoader)\n").is_valid
    assert ASTGuardValidator.validate_code_edit("", "import yaml\ndef parse_c(d: str):\n    return yaml.load(d, yaml.CSafeLoader)\n").is_valid
    assert ASTGuardValidator.validate_code_edit("", "import yaml\ndef parse_a(d: str):\n    return yaml.load_all(d)\n").is_valid is False
    assert ASTGuardValidator.validate_code_edit("", "import yaml\ndef parse_u(d: str):\n    return yaml.unsafe_load(d)\n").is_valid is False

    evasion_vectors = [
        'def f():\n    return compile("x=1", "<str>", "exec")\n',
        'def f():\n    return getattr(__builtins__, f"{\'ev\'}al")\n',
        'def f():\n    return getattr(__builtins__, "".join(["ev", "al"]))\n',
        'def f():\n    return __builtins__["eval"]\n',
        'import builtins\ndef f():\n    return builtins.__dict__["exec"]\n',
        'import importlib\ndef f():\n    return importlib.import_module("os")\n',
        'import operator\ndef f():\n    return operator.attrgetter("eval")\n',
        'import os\ndef f():\n    return os.execv("/bin/sh", ["sh"])\n',
        'import os\ndef f():\n    return os.spawnv(0, "/bin/sh", ["sh"])\n',
        'def f():\n    return __builtins__.__getattribute__("".join(["ev", "al"]))("1")\n',
        'def f():\n    fn = "".join(["ev", "al"])\n    return __builtins__.__getattribute__(fn)("1")\n',
        'def f():\n    return object.__getattribute__(__builtins__, "".join(["ev", "al"]))("1")\n',
        'import os\ndef f():\n    return (x := os).system("id")\n',
        'import os, subprocess\ndef f():\n    a, b = os, subprocess\n    return a.system("id")\n',
        'import builtins\ndef f():\n    fn = "".join(reversed("lave"))\n    return getattr(builtins, fn)("1")\n',
        'import builtins\ndef f():\n    fn = chr(101) + "val"\n    return getattr(builtins, fn)("1")\n',
        'import builtins\ndef f():\n    fn = "lave"[::-1]\n    return getattr(builtins, fn)("1")\n',
        'import sys\ndef f():\n    return sys.modules.get("os").system("id")\n',
        'import sys\ndef f():\n    return sys.modules["os"].system("id")\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=not {})\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=bool(1))\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=(1 if True else 0))\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=(False or True))\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=(True and True))\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=~0)\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=-1)\n',
        'import subprocess\ndef f():\n    return subprocess.run(["cmd"], shell=not [])\n',
        'import subprocess\ndef f():\n    truth = 1\n    return subprocess.run(["cmd"], shell=truth)\n',
        'import importlib\ndef f():\n    return importlib.import_module(name="os")\n',
        'def f():\n    return open(file="../secret.txt")\n',
        'def f():\n    return __import__(name="os")\n',
        'import os\ndef f(b):\n    return os.path.join(b, "../secret.txt")\n',
        'from pathlib import Path\ndef f(b):\n    return Path(b).joinpath("..", "etc")\n',
        'from pathlib import Path\ndef f(b):\n    return Path(b) / "../secret"\n',
        'import pty\ndef f():\n    return pty.spawn("/bin/sh")\n',
        'import asyncio\nasync def f():\n    return await asyncio.create_subprocess_shell("id")\n',
        'import subprocess\ndef f():\n    return subprocess.getoutput("id")\n',
        'import subprocess\ndef f(kw):\n    return subprocess.run(["echo"], **kw)\n',
        'def f(cur, uid):\n    return cur.execute(f"SELECT * FROM u WHERE id={uid}")\n',
        'def f(cur, uid):\n    return cur.executemany(f"DELETE FROM u WHERE id={uid}")\n',
        'def q(cur, uid):\n    return cur.execute("SELECT * FROM u WHERE id=%s" % uid)\n',
        'def q(cur, uid):\n    return cur.execute("DELETE FROM u WHERE id={}".format(uid))\n',
        'def q(cur, uid):\n    return cur.execute("UPDATE u SET name=" + uid)\n',
        'def q(cur, uid):\n    return cur.execute(sql="SELECT * FROM u WHERE id=" + uid)\n',
        f'from {t_umock} import {t_mock}\ndef f():\n    return {t_mock}()\n',
    ]
    _assert_sast_blocked(evasion_vectors, target_file="scripts/sample_mod.py")
    _assert_sast_blocked([
        "import subprocess as sp\ndef run_bad() -> None:\n    sp.Popen(['cmd', '/c', 'dir'], shell=True)\n",
        "from subprocess import Popen as spawn_cmd\ndef run_bad2() -> None:\n    spawn_cmd('echo 1', shell=True)\n",
        "import pickle as pkl\ndef load_bad(raw: bytes):\n    return pkl.loads(raw)\n",
        "import os as operating_sys\ndef sys_bad() -> int:\n    return operating_sys.system('whoami')\n",
    ], target_file="src/alias_evasion.py")

    # global/nonlocal scope + safe shells/SQL + self_validator checks
    assert ASTGuardValidator.validate_code_edit("", "def outer_fn() -> int:\n    global GLOBAL_SHARED_STATE\n    def inner_fn() -> int:\n        nonlocal ENCLOSING_STATE\n        return GLOBAL_SHARED_STATE + ENCLOSING_STATE\n    return inner_fn()\n").is_valid
    assert ASTGuardValidator.validate_code_edit("", 'import subprocess\ndef f():\n    return subprocess.run(["echo"], shell=not True)\n').is_valid
    assert ASTGuardValidator.validate_code_edit("", 'def q(cur, uid):\n    return cur.execute("SELECT * FROM u WHERE id=?", (uid,))\n', target_file="scripts/db_repo.py").is_valid

    self_path = "scripts/_internal/ast_guard_validator/helper.py"
    assert ASTGuardValidator.check_sast_constructs('def tok() -> str:\n    return "ev" + "al"\n', target_file=self_path) == []
    _assert_sast_blocked([
        "def bad_eval(x: str):\n    return " + "ev" + "al(x)\n",
        "def bad_exec(x: str):\n    return " + "ex" + "ec(x)\n",
        'import subprocess\ndef bad_sp() -> None:\n    subprocess.run(["echo"], shell=True)\n',
    ], target_file=self_path)

    # Migrated from test_resilience_sast_call_matrix_and_router_handoff
    sast_matrix_src = "\n".join([
        "import marshal, os, pathlib, pickle, subprocess, yaml",
        f"from yaml import SafeLoader\nfrom operator import attrgetter\nfrom {t_umock} import {t_mock}, patch",
        "def probe(s, b, kw, dyn_name, obj):",
        "    subprocess.getoutput('ls'); subprocess.run(['ls'], **kw)",
        "    subprocess.Popen('a', 0, None, None, None, None, None, False, True)",
        "    yaml.unsafe_load(s); yaml.full_load(s); yaml.load(s)",
        "    yaml.load(s, yaml.SafeLoader); yaml.load(s, Loader=SafeLoader)",
        "    open('../secret.txt'); pathlib.Path('../secret.txt'); os.path.join('dir', '../secret.txt')",
        "    attrgetter('lave'[::-1]); attrgetter('__subclasses__')",
        "    __import__('so'[::-1]); __import__('subprocess')",
        "    getattr(os, dyn_name); getattr(obj, 'lave'[::-1]); getattr(globals(), 'x')",
        f"    os.execv('/bin/sh', ['sh']); pickle.loads(b); marshal.loads(b); patch('a.b')\n    return {t_mock}()",
    ])
    assert len(ASTGuardValidator.check_sast_constructs(sast_matrix_src)) >= 14

    # Additional missing branches: taint clearing + remaining SAST evasion/gaming vectors
    taint_cleared = "import os\ndef f(cur, u):\n    q = f'SELECT * FROM t WHERE id={u}'\n    q = 'SELECT 1'\n    cur.execute(q)\n    x = os\n    x = 1\n    return x\n"
    assert ASTGuardValidator.check_sast_constructs(taint_cleared, target_file="src_app/mod.py") == []
    assert ASTGuardValidator.check_sast_constructs("def f(items):\n    a, b = items\n    return a\n", target_file="src_app/mod.py") == []
    _assert_sast_blocked(["def f(self): return len(self.grants) >= 12\n"], target_file="src/mod.py")
    extra_blocked = [
        "def f(): return vars()['eval']\n",
        "def f(): return locals()['exec']\n",
        "def f(x): return getattr(x, '__globals__')\n",
        "def f(frame): return frame.f_locals\n",
        "def f(): return globals()['__builtins__']\n",
        "import operator\ndef f(): return operator.methodcaller('system')\n",
        "def f(xs): return list(map(eval, xs))\n",
        "import functools, os\ndef f(): return functools.partial(os.execv, '/bin/sh')\n",
        "import functools, pickle\ndef f(): return functools.partial(func=pickle.loads)\n",
        "import ctypes\ndef f(): return getattr(ctypes, 'windll')\n",
        "from ctypes import windll\ndef f(): return windll\n",
        "import os\ndef f(): return os.system\n",
        "import sys, inspect\ndef f():\n    a = sys.modules.get('pytest')\n    b = 'pytest' in sys.modules\n    return inspect.currentframe()\n",
        f'def f(): return ("{t_pytest[:7]}" + "{t_pytest[7:]}")\n',
        'def f(): return "C:/dev/" + "NK_External_Projects/app"\n',
    ]
    _assert_sast_blocked(extra_blocked, target_file="src_app/mod.py")


def _assert_scope_creep_allowed_files(tmp_path: Path) -> None:
    stg = tmp_path / ".staging"
    ok_file, nested_file, outside_file = stg / "scripts" / "target.py", stg / "scripts" / "sub" / "nested.py", tmp_path / "outside" / "escape.py"
    assert qd_chk.check_allowed_files([ok_file], stg, ["scripts/*.py"]) == []
    nested_block = qd_chk.check_allowed_files([ok_file, nested_file], stg, ["scripts/*.py"])
    assert (len(nested_block), nested_block[0].rule_id, nested_block[0].file_path) == (1, "QD-SCOPE-CREEP", "scripts/sub/nested.py")
    assert qd_chk.check_allowed_files([ok_file, nested_file], stg, ["scripts/**/*.py"]) == []
    escape_block = qd_chk.check_allowed_files([outside_file], stg, ["**/*.py"])
    assert (len(escape_block), escape_block[0].rule_id) == (1, "QD-SCOPE-CREEP")


@pytest.mark.fast
def test_quality_diff_and_scope_creep_gates(tmp_path: Path) -> None:
    """Rileva regressioni CC, nesting, except silenzioso, tautologie, pytest.skip e scope-creep."""
    base_fn = "def score(x: int) -> int:\n    if x < 0:\n        return 0\n    if x == 0:\n        return 0\n    return x + 1\n"
    high_cc = "def score(x: int) -> int:\n    if x > 0:\n        for i in range(x):\n            if i > 1:\n                while i > 0:\n                    if i % 2 == 0:\n                        return i\n                    i -= 1\n    return 0\n"
    silent_exc = "def score(x: int) -> int:\n    try:\n        return x\n    except Exception:\n        pass\n"
    clean_simpler = "def score(x: int) -> int:\n    return x + 1 if x > 0 else 0\n"

    cc_rules = {v.rule_id for v in qd_chk.check_python_quality_diff(base_fn, high_cc, "mod.py")}
    assert ("QD-CC-REGRESSION" in cc_rules, "QD-NESTING-REGRESSION" in cc_rules) == (True, True)
    assert "QD-SILENT-EXCEPT" in {v.rule_id for v in qd_chk.check_python_quality_diff(base_fn, silent_exc, "mod.py")}
    assert "QD-TAUTOLOGICAL-ASSERT" in {v.rule_id for v in qd_chk.check_python_quality_diff("def test_val():\n    val = 2\n    assert val == 2\n", "def test_val():\n    assert True\n", "tests/test_x.py")}
    assert (qd_chk.check_python_quality_diff(base_fn, base_fn, "mod.py"), qd_chk.check_python_quality_diff(base_fn, clean_simpler, "mod.py")) == ([], [])
    assert qd_chk.compute_file_delta_cc(base_fn, clean_simpler) < 0
    assert "QD-ZERO-ASSERT-TEST" in {v.rule_id for v in qd_chk.check_python_quality_diff("", "import pytest\n\ndef test_skipped_only() -> None:\n    pytest.skip('not implemented')\n", "tests/test_sample.py")}
    assert "QD-TAUTOLOGICAL-ASSERT" in {v.rule_id for v in qd_chk.check_python_quality_diff("", "def test_same() -> None:\n    val = 5\n    assert val == val\n", "tests/test_sample.py")}
    _assert_scope_creep_allowed_files(tmp_path)


def _assert_frontend_lexer_and_replace_hunks() -> None:
    lexer_edge_src = 'const esc = "a\\\\\\"b";\nconst rx = /[/a-z]/gi;\nconst ratio = a / b;\n/* multi\nline */\nconst a = 1;\n'
    assert fe_chk.scan_frontend_code(lexer_edge_src, "src/lex.ts") == []
    assert fe_chk._strip_comments_preserve_lines('const s = "abc') == 'const s = "abc'
    rep_viols = fe_chk.scan_frontend_code("const ok = 1;\nconst bad = (x as any) + 1;\n", "src/mod.tsx", pre_code="const ok = 1;\nconst bad = (x as any);\n")
    assert (len(rep_viols), rep_viols[0].rule_id, rep_viols[0].line_number) == (1, "FE-TS-BYPASS", 2)


@pytest.mark.fast
def test_frontend_static_checker_lexer_css_and_diff() -> None:
    """Blocca eval/XSS/as any/@ts-ignore/hex, gestisce regex JS vs divisione e diff hunk."""
    bad_tsx = "// @ts-ignore\nconst fn = (raw: unknown, s: string) => {\n  const obj = raw as any;\n  const badge = '#ff00aa';\n  return " + "ev" + "al(s) || obj;\n};\n"
    assert {"FE-DYNAMIC-EXEC", "FE-TS-BYPASS", "FE-INLINE-HEX"}.issubset({v.rule_id for v in fe_chk.scan_frontend_code(bad_tsx, "src/App.tsx")})
    assert fe_chk.scan_frontend_code("export const addNumbers = (a: number, b: number): number => a + b;\n", "src/App.tsx") == []
    assert fe_chk.scan_frontend_code(":root {\n  --nk-accent: #2563eb;\n}\n.btn { color: var(--nk-accent); }\n", "src/theme.css") == []
    assert {"FE-INLINE-HEX", "FE-CSS-UNSAFE-URL"}.issubset({v.rule_id for v in fe_chk.scan_frontend_code(".btn { color: #ff0000; background: url(javascript:void(0)); }\n", "src/theme.css")})
    viols = fe_chk.scan_frontend_code("const pat = /\\/\\*/;\nconst runUnsafe = (s: string) => " + "ev" + "al(s);\n", "src/parser.ts")
    assert any(v.rule_id == "FE-DYNAMIC-EXEC" and v.line_number == 2 for v in viols)
    assert fe_chk.scan_frontend_code("/* " + "ev" + "al(x) */\nexport const safeVal = 1;\n", "src/parser.ts") == []
    pre_tsx = "export const legacy = (x: unknown) => x as any;\n"
    assert fe_chk.scan_frontend_code(pre_tsx + "export const add = (a: number, b: number): number => a + b;\n", "src/legacy.tsx", pre_code=pre_tsx) == []
    diff_viols = fe_chk.scan_frontend_code(pre_tsx + "export const badNew = (y: unknown) => y as any;\n", "src/legacy.tsx", pre_code=pre_tsx)
    assert (len(diff_viols), diff_viols[0].rule_id, diff_viols[0].line_number) == (1, "FE-TS-BYPASS", 2)
    _assert_frontend_lexer_and_replace_hunks()


def _assert_ast_guard_cli_errors_and_migrated(tmp_path: Path, clean_prod: Path) -> None:
    bad_bytes = tmp_path / "broken_utf8.py"
    bad_bytes.write_bytes(b"\xff\xfe\x00\x00invalid")
    rc_err, stdout_err, _ = call_script_main_captured(_agv_mod, ["--target", str(bad_bytes)])
    assert (rc_err, "Could not read file" in stdout_err) == (1, True)
    err_json = tmp_path / "err_out.json"
    rc_miss, stdout_miss, _ = call_script_main_captured(_agv_mod, ["--target", str(tmp_path / "nope.py"), "--json", "--output-json", str(err_json)])
    assert (rc_miss, json.loads(stdout_miss)["passed"], err_json.is_file()) == (2, False, True)
    rc_empty, stdout_empty, _ = call_script_main_captured(_agv_mod, ["--target", "   "])
    assert (rc_empty, "Empty target/stage-dir path" in stdout_empty) == (2, True)
    rc_notdir, stdout_notdir, _ = call_script_main_captured(_agv_mod, ["--stage-dir", str(clean_prod)])
    assert (rc_notdir, ("not a directory" in stdout_notdir or "ERROR" in stdout_notdir)) == (2, True)

    clean_stg = tmp_path / "clean_staging"
    (clean_stg / "scripts").mkdir(parents=True)
    (clean_stg / "scripts" / "pure.py").write_text("def compute(x: int) -> int:\n    fn = lambda v: v + 1\n    return fn(x)\n", encoding="utf-8")
    rc_ag, out_ag, _ = call_script_main_captured(_agv_mod, ["--stage-dir", str(clean_stg), "--json"])
    assert (rc_ag, json.loads(out_ag)["passed"]) == (0, True)
    bad_dir = tmp_path / "src"
    bad_dir.mkdir(parents=True)
    tok_ev, tok_pytest = "ev" + "al", "PYTEST_" + "CURRENT_TEST"
    (bad_dir / "bad_app.py").write_text(f"import os\nx = os.environ.get('{tok_pytest}')\ngrants = [1, 2]\nif len(grants) >= 12:\n    pass\nk = '{tok_ev[::-1]}'[::-1]\n", encoding="utf-8")
    assert call_script_main_captured(_agv_mod, ["--target", str(bad_dir)])[0] != 0
    assert ASTGuardValidator().validate_code_edit(
        "def f(a: int | str) -> int | None:\n    x: int | str = 1\n    return 1\n",
        "def f(a: int | str) -> int | None:\n    x: int | str = 2\n    return 2\n",
        target_file="scripts/u.py",
    ).is_valid is True


@pytest.mark.integration
def test_ast_guard_cli_stage_dir_all_and_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_nk_env: Path) -> None:
    """Esercita ast_guard_validator.main() con --stage-dir, --quality-diff, --target all, posizionale ed errori."""
    _ = isolated_nk_env
    with pytest.raises(AttributeError):
        getattr(_agv_mod, "NON_EXISTENT_AGV_SYMBOL")

    ws = tmp_path / "mini_agv_ws"
    (ws / "scripts").mkdir(parents=True)
    (ws / ".staging" / "scripts").mkdir(parents=True)
    (ws / ".staging" / "src_app").mkdir(parents=True)
    (ws / "scripts" / "svc.py").write_text("def add_one(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    (ws / ".staging" / "scripts" / "svc.py").write_text("def add_one(x: int) -> int:\n    return x + 1\n", encoding="utf-8")

    out_ok = tmp_path / "agv_ok.json"
    rc_ok, stdout_ok, _ = call_script_main_captured(_agv_mod, ["--stage-dir", str(ws / ".staging"), "--quality-diff", "--allowed-files", "scripts/*.py", "--output-json", str(out_ok), "--json"])
    assert (rc_ok, json.loads(stdout_ok)["passed"], json.loads(out_ok.read_text(encoding="utf-8"))["quality_diff_violations"]) == (0, True, 0)

    (ws / ".staging" / "scripts" / "extra.py").write_text("def bad_fn():\n    try:\n        return 1\n    except Exception:\n        pass\n", encoding="utf-8")
    (ws / ".staging" / "src_app" / "view.tsx").write_text("export const c = '#ff00aa';\n", encoding="utf-8")
    rc_fail, stdout_fail, _ = call_script_main_captured(_agv_mod, ["--stage-dir", str(ws / ".staging"), "--quality-diff", "--allowed-files", "scripts/svc.py"])
    assert (rc_fail, "[QUALITY-DIFF:" in stdout_fail, "FAILED:" in stdout_fail) == (1, True, True)

    ws_all = tmp_path / "mini_all_ws"
    (ws_all / "scripts").mkdir(parents=True)
    (ws_all / "tests").mkdir(parents=True)
    clean_prod = ws_all / "scripts" / "svc.py"
    clean_prod.write_text("def add_one(x: int) -> int:\n    return x + 1\n", encoding="utf-8")
    (ws_all / "tests" / "test_svc.py").write_text("def test_add_one():\n    assert 2 + 1 == 3\n", encoding="utf-8")
    monkeypatch.chdir(ws_all)
    rc_all, stdout_all, _ = call_script_main_captured(_agv_mod, ["--target", "all", "--json"])
    assert (rc_all, json.loads(stdout_all)["files_scanned"] >= 2) == (0, True)
    rc_pos, stdout_pos, _ = call_script_main_captured(_agv_mod, [str(clean_prod)])
    assert (rc_pos, "PASSED DETERMINISTIC AST GUARD" in stdout_pos) == (0, True)
    _assert_ast_guard_cli_errors_and_migrated(tmp_path, clean_prod)


@pytest.mark.fast
def test_reexports_lazy_map_catalog_and_import_roots(tmp_path: Path) -> None:
    """Verifica _LAZY_EXPORT_MAP staging/prod, validate_pydantic_catalog_records e import roots."""
    from _internal.ast_guard_validator.quality_diff_rules import QualityDiffViolation

    prod_sub = tmp_path / "scripts" / "_internal" / "demo_pkg" / "sub.py"
    prod_sub.parent.mkdir(parents=True)
    prod_sub.write_text("def calc(x: int) -> int:\n    return x + 1\n", encoding="utf-8")

    stg_sub = tmp_path / ".staging" / "scripts" / "_internal" / "demo_pkg" / "sub.py"
    stg_sub.parent.mkdir(parents=True)
    stg_sub.write_text("def calc(x: int, y: int) -> int:\n    return x + y\n", encoding="utf-8")

    facade_path = tmp_path / ".staging" / "scripts" / "demo_facade.py"
    pre_facade = '_LAZY_EXPORT_MAP = {"calc": ("_internal.demo_pkg.sub", "calc")}\n'
    post_facade = '_LAZY_EXPORT_MAP = {"calc": ("_internal.demo_pkg.sub", "calc"), "miss": ("_internal.demo_pkg.missing", "miss")}\n'
    facade_path.write_text(post_facade, encoding="utf-8")
    rep = ASTGuardValidator.validate_code_edit(pre_facade, post_facade, target_file=str(facade_path))
    assert rep.is_valid is False and any("calc" in v.message for v in rep.violations)

    res_p = reexp_mod.validate_pydantic_catalog_records(
        [{"rule_id": "R1", "file_path": "a.py", "message": "ok"}, {"rule_id": 123, "file_path": "b.py", "message": "bad"}],
        QualityDiffViolation,
    )
    assert res_p["passed"] is False and res_p["valid_records"] == 1 and res_p["invalid_records"] == 1
    assert reexp_mod.validate_pydantic_catalog_records([{"name": "item_a", "score": 10}], _CatalogItemSample)["passed"] is True

    hub = tmp_path / "hub_roots"
    (hub / "scripts").mkdir(parents=True)
    stg_scripts = hub / ".staging" / "scripts"
    stg_scripts.mkdir(parents=True)
    facade_file = stg_scripts / "facade_entry.py"
    facade_file.write_text("X = 1\n", encoding="utf-8")
    direct_stg = hub / ".staging" / "root_mod.py"
    direct_stg.write_text("X = 1\n", encoding="utf-8")

    roots_stg, cur_stg = reexp_mod._resolve_local_import_roots(str(facade_file))
    assert (hub / ".staging" / "scripts") in roots_stg and cur_stg == stg_scripts
    assert reexp_mod._resolve_prod_import_roots(str(facade_file))[0] == [hub / "scripts"]
    assert reexp_mod._resolve_local_import_roots("<target>") == ([], None) and reexp_mod._resolve_prod_import_roots("<target>") == ([], None)
    assert reexp_mod._resolve_local_import_roots(str(direct_stg))[0] and reexp_mod._resolve_prod_import_roots(str(direct_stg))[0] == [hub / "scripts"]


@pytest.mark.fast
def test_reexports_star_type_checking_cycles_and_cache(tmp_path: Path) -> None:
    """Esercita _iter_top_level_import_from, star re-export, cicli e cache in reexports.py."""
    hub = tmp_path / "hub_reexp"
    prod_pkg, stg_scripts = hub / "scripts" / "pkg", hub / ".staging" / "scripts"
    prod_pkg.mkdir(parents=True)
    stg_scripts.mkdir(parents=True)
    (prod_pkg / "__init__.py").write_text("", encoding="utf-8")
    (prod_pkg / "base_mod.py").write_text(
        "GLOBAL_CONST = 1\nclass ExportedBox:\n    class NestedMeta:\n        pass\n"
        "    def run(self, x: int) -> int:\n        return x + 1\n"
        "def exported_fn(a: int) -> int:\n    return a\n"
        "def _private_fn() -> int:\n    return 0\n",
        encoding="utf-8",
    )
    (prod_pkg / "broken_mod.py").write_text("def broken(:\n", encoding="utf-8")
    (prod_pkg / "cycle_a.py").write_text("from .cycle_b import B_VAL\nA_VAL = 1\n", encoding="utf-8")
    (prod_pkg / "cycle_b.py").write_text("from .cycle_a import A_VAL\nB_VAL = 2\n", encoding="utf-8")

    facade_src = (
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from pkg.never_loaded import Ghost\n"
        "else:\n    from pkg.cycle_a import A_VAL\n"
        "if not TYPE_CHECKING:\n    from pkg.base_mod import *\n"
        "try:\n    from pkg.base_mod import exported_fn as fn_alias\n    from pkg.broken_mod import anything\n"
        "except ImportError:\n    pass\n"
        "_LAZY_EXPORT_MAP = {'lazy_box': ('pkg.base_mod', 'ExportedBox')}\n"
    )
    facade_file = stg_scripts / "facade_entry.py"
    facade_file.write_text(facade_src, encoding="utf-8")
    roots_stg, cur_stg = reexp_mod._resolve_local_import_roots(str(facade_file))

    tree = ast.parse(facade_src)
    assert not any(n.module == "pkg.never_loaded" for n in reexp_mod._iter_top_level_import_from(tree))
    collector = sig_mod.SignatureCollector()
    cache: dict = {}
    reexp_mod._resolve_local_import_exports(tree, collector, roots_stg, cur_stg, skip_unparse=True, visited=set(), cache=cache)
    assert {"ExportedBox", "lazy_box"}.issubset(collector.classes)
    assert {"ExportedBox.run", "fn_alias"}.issubset(collector.signatures) and "_private_fn" not in collector.signatures
    assert "exported_fn" in reexp_mod._collect_resolved_module(prod_pkg / "base_mod.py", roots_stg, skip_unparse=True, visited=set(), cache=cache).signatures


@pytest.mark.fast
def test_validator_helpers_signature_class_and_counterpart_edges(tmp_path: Path) -> None:
    """Esercita validator_helpers.py su mutazioni firme, classi, controparte staging e JSON atomico."""
    pre_cls = "class BaseA:\n    pass\nclass Derived(BaseA):\n    pass\nclass DeletedPublic:\n    pass\nclass _InternalHidden:\n    pass\n"
    post_cls = "class BaseA:\n    pass\nclass Derived:\n    pass\n"
    rep_cls = ASTGuardValidator.validate_code_edit(pre_cls, post_cls)
    assert rep_cls.is_valid is False and {ViolationType.UNAUTHORIZED_DELETION, ViolationType.SIGNATURE_MUTATION}.issubset({v.violation_type for v in rep_cls.violations})
    assert ASTGuardValidator.validate_code_edit(pre_cls, post_cls, allowed_mutations={"DeletedPublic", "Derived"}).is_valid is True

    pre_sigs = "def flip_async(x: int) -> int:\n    return x\ndef pos_only(a: int, /, b: int) -> int:\n    return a + b\ndef drop_default(a: int = 1) -> int:\n    return a\ndef drop_var(*args, **kwargs) -> int:\n    return 1\ndef bad_ann(val: int) -> int:\n    return val\n"
    post_sigs = "async def flip_async(x: int) -> int:\n    return x\ndef pos_only(a: int, b: int) -> int:\n    return a + b\ndef drop_default(a: int) -> int:\n    return a\ndef drop_var() -> int:\n    return 1\ndef bad_ann(val: str) -> int:\n    return int(val)\n"
    rep_sigs = ASTGuardValidator.validate_code_edit(pre_sigs, post_sigs)
    assert {"flip_async", "pos_only", "drop_default", "drop_var", "bad_ann:val"}.issubset({v.symbol_name for v in rep_sigs.violations})

    hub = tmp_path / "vh_hub"
    prod_f, stg_f = hub / "scripts" / "target.py", hub / ".staging" / "scripts" / "target.py"
    prod_f.parent.mkdir(parents=True)
    stg_f.parent.mkdir(parents=True)
    prod_f.write_text("X = 1\n", encoding="utf-8")
    stg_f.write_text("X = 2\n", encoding="utf-8")
    assert vhelp_mod._resolve_production_counterpart(stg_f, hub) == prod_f.resolve()
    assert vhelp_mod._resolve_production_counterpart(hub / ".staging" / "scripts" / "new_only.py", hub) is None

    out_json = tmp_path / "sub" / "rep.json"
    vhelp_mod._write_json_atomic(out_json, {"ok": True})
    assert json.loads(out_json.read_text(encoding="utf-8")) == {"ok": True}
    blocking_file = tmp_path / "file_not_dir"
    blocking_file.write_text("x", encoding="utf-8")
    with pytest.raises(OSError):
        vhelp_mod._write_json_atomic(blocking_file / "rep.json", {"ok": False})
