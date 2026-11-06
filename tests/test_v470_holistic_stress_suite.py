# -*- coding: utf-8 -*-
"""
Suite permanente di stress olistico (12 test Zero-Mock) per Nexus Keystone v4.7.0-STE100-Unified.
Modulo: tests/test_v470_holistic_stress_suite.py.
Valida le correzioni avversarie delle 6 batterie S1, S2, S3, S4 e S6 senza mock.
"""

from __future__ import annotations

import concurrent.futures
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_THIS_FILE = Path(__file__).resolve()
_WORKSPACE_ROOT = _THIS_FILE.parent.parent
if _WORKSPACE_ROOT.name == ".staging":
    _WORKSPACE_ROOT = _WORKSPACE_ROOT.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))


def _load_staged_or_prod(mod_name: str, rel_script: str) -> Any:
    """Carica dinamicamente il modulo dando priorita a .staging/scripts/."""
    staged = _WORKSPACE_ROOT / ".staging" / rel_script
    target = staged if staged.exists() else (_WORKSPACE_ROOT / rel_script)
    spec = importlib.util.spec_from_file_location(mod_name, str(target))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_s1_01_hook_gate_blocks_staging_exfiltration_to_production(
    tmp_path: Path,
) -> None:
    """S1-01: Verifica che Copy-Item da .staging/ verso scripts/ di produzione sia bloccato con deny."""
    hg = _load_staged_or_prod("nk_hook_gate_s1_01", "scripts/nk_hook_gate.py")
    res = hg._handle_write_gate(
        payload={"toolName": "run_command"},
        project_root=tmp_path,
        strict_external=True,
        cli_target="",
        cli_cmd="Copy-Item .staging/evil.py scripts/nk_hook_gate.py",
        cli_content="",
    )
    assert res.get("decision") == "deny"


def test_s1_02_hook_gate_blocks_nested_fake_staging_directory(
    tmp_path: Path,
) -> None:
    """S1-02: Verifica che il falso percorso annidato scripts/.staging/backdoor.py sia bloccato."""
    hg = _load_staged_or_prod("nk_hook_gate_s1_02", "scripts/nk_hook_gate.py")
    res = hg._handle_write_gate(
        payload={"toolName": "write_file"},
        project_root=tmp_path,
        strict_external=True,
        cli_target=str(tmp_path / "scripts" / ".staging" / "backdoor.py"),
        cli_cmd="",
        cli_content="print(1)",
    )
    assert res.get("decision") == "deny"


def test_s1_03_hook_gate_blocks_authorized_script_comment_spoofing(
    tmp_path: Path,
) -> None:
    """S1-03: Verifica che citare # ast_repo_mapper.py in un commento non autorizzi Set-Content su scripts/."""
    hg = _load_staged_or_prod("nk_hook_gate_s1_03", "scripts/nk_hook_gate.py")
    res = hg._handle_write_gate(
        payload={"toolName": "run_command"},
        project_root=tmp_path,
        strict_external=True,
        cli_target="",
        cli_cmd="Set-Content scripts/x.py '# ast_repo_mapper.py'",
        cli_content="",
    )
    assert res.get("decision") == "deny"


def test_s1_04_hook_gate_blocks_powershell_dotnet_io_file_writes(
    tmp_path: Path,
) -> None:
    """S1-04: Verifica il blocco di [System.IO.File]::WriteAllText e New-Item verso scripts/."""
    hg = _load_staged_or_prod("nk_hook_gate_s1_04", "scripts/nk_hook_gate.py")
    for cmd_str in (
        "[System.IO.File]::WriteAllText('scripts/x.py', '1')",
        "New-Item scripts/x.py -Value '1'",
    ):
        res = hg._handle_write_gate(
            payload={"toolName": "run_command"},
            project_root=tmp_path,
            strict_external=True,
            cli_target="",
            cli_cmd=cmd_str,
            cli_content="",
        )
        assert res.get("decision") == "deny", f"Mancato blocco per: {cmd_str}"


def test_s1_05_hook_gate_protects_historical_patch_notes_sections(
    tmp_path: Path,
) -> None:
    """S1-05: Verifica che la rimozione di una sezione storica ## [v4.5.2] in PATCH_NOTES.md sia negata."""
    hg = _load_staged_or_prod("nk_hook_gate_s1_05", "scripts/nk_hook_gate.py")
    pn_file = tmp_path / "PATCH_NOTES.md"
    pn_file.write_text(
        "# Patch Notes\n\n## [v4.6.0] - 2026-10-30\n- Feat A\n\n## [v4.5.2] - 2026-10-25\n- Feat B\n",
        encoding="utf-8",
    )
    res = hg._handle_write_gate(
        payload={"toolName": "write_file"},
        project_root=tmp_path,
        strict_external=True,
        cli_target=str(pn_file),
        cli_cmd="",
        cli_content="# Patch Notes\n\n## [v4.7.0] - 2026-10-31\n- New\n\n## [v4.6.0] - 2026-10-30\n- Feat A\n",
    )
    assert res.get("decision") == "deny"
    assert "prepend-only" in res.get("reason", "")


def test_s1_06_hook_gate_resilient_to_corrupt_integrity_json(
    tmp_path: Path,
) -> None:
    """S1-06: Verifica che un file {conv_id}_integrity.json corrotto non sollevi eccezioni non gestite."""
    hg = _load_staged_or_prod("nk_hook_gate_s1_06", "scripts/nk_hook_gate.py")
    hooks_dir = tmp_path / "hooks_tmp"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    prev_hooks_dir = os.environ.get("NK_HOOKS_TEMP_DIR")
    os.environ["NK_HOOKS_TEMP_DIR"] = str(hooks_dir)
    try:
        corrupt_file = hooks_dir / "conv_corrupt_integrity.json"
        corrupt_file.write_text("{corrupt_json_not_valid", encoding="utf-8")

        rc = hg.main(
            [
                "integrity",
                "--check",
                "--project-root",
                str(tmp_path),
                "--conversation-id",
                "conv_corrupt",
            ]
        )
        assert rc in (0, 1)
    finally:
        if prev_hooks_dir is None:
            os.environ.pop("NK_HOOKS_TEMP_DIR", None)
        else:
            os.environ["NK_HOOKS_TEMP_DIR"] = prev_hooks_dir


def test_s2_01_win32_2pc_atomic_batch_rollback_on_invalid_deleted_files(
    tmp_path: Path,
) -> None:
    """S2-01: Verifica il rollback atomico completo se .deleted_files.json contiene path traversal ../../outside.txt."""
    w2pc = _load_staged_or_prod("win32_2pc_s2_01", "scripts/win32_2pc_engine.py")
    repo_root = tmp_path / "repo"
    stg_dir = repo_root / ".staging"
    (repo_root / "nk_genome").mkdir(parents=True, exist_ok=True)
    (repo_root / "nk_tracking").mkdir(parents=True, exist_ok=True)
    (stg_dir / "nk_genome").mkdir(parents=True, exist_ok=True)

    prod_doc = repo_root / "nk_genome" / "concept_map.md"
    prod_doc.write_text("ORIGINAL_CONCEPT_MAP", encoding="utf-8")

    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("DO_NOT_DELETE", encoding="utf-8")

    (stg_dir / "nk_genome" / "concept_map.md").write_text(
        "MODIFIED_CONCEPT_MAP", encoding="utf-8"
    )
    (stg_dir / ".deleted_files.json").write_text(
        json.dumps(["../../outside.txt"]), encoding="utf-8"
    )

    with pytest.raises((ValueError, w2pc.TwoPhaseCommitError)):
        w2pc.promote_staging_to_production(
            repo_root=str(repo_root),
            verify_baseline=False,
        )

    assert prod_doc.read_text(encoding="utf-8") == "ORIGINAL_CONCEPT_MAP"
    assert outside_file.is_file()


def test_s2_02_win32_2pc_wal_recover_and_deleted_files_anchor(
    tmp_path: Path,
) -> None:
    """S2-02: Verifica WriteAheadLogManager.recover() e la registrazione di deleted_files in session_anchor.jsonl."""
    w2pc = _load_staged_or_prod("win32_2pc_s2_02", "scripts/win32_2pc_engine.py")
    repo_root = tmp_path / "repo_del"
    stg_dir = repo_root / ".staging"
    (repo_root / "tests").mkdir(parents=True, exist_ok=True)
    (repo_root / "nk_tracking").mkdir(parents=True, exist_ok=True)
    (stg_dir / "nk_genome").mkdir(parents=True, exist_ok=True)

    wal_mgr = w2pc.WriteAheadLogManager()
    recovered = wal_mgr.recover(repo_root)
    assert isinstance(recovered, list)

    obsolete_test = repo_root / "tests" / "test_obsolete_dummy.py"
    obsolete_test.write_text("# obsolete\n", encoding="utf-8")
    (stg_dir / "nk_genome" / "idea_canvas.md").write_text(
        "# Idea Canvas v4.7.0\n", encoding="utf-8"
    )
    (stg_dir / ".deleted_files.json").write_text(
        json.dumps(["tests/test_obsolete_dummy.py"]), encoding="utf-8"
    )

    res = w2pc.promote_staging_to_production(
        repo_root=str(repo_root),
        verify_baseline=False,
    )
    assert not obsolete_test.exists()
    assert "tests/test_obsolete_dummy.py" in res.get("deleted_files", [])

    anchor_file = repo_root / "nk_tracking" / "anchor" / "session_anchor.jsonl"
    assert anchor_file.is_file()
    anchor_data = json.loads(anchor_file.read_text(encoding="utf-8").splitlines()[-1])
    assert "tests/test_obsolete_dummy.py" in anchor_data.get("deleted_files", [])


def test_s3_01_memory_3tier_concurrent_append_zero_loss(
    tmp_path: Path,
) -> None:
    """S3-01: Verifica che 8 thread concorrenti x 5 episodi salvino 40/40 episodi con zero PermissionError."""
    mem_mod = _load_staged_or_prod(
        "memory_3tier_s3_01", "scripts/memory_3tier_engine.py"
    )
    engine = mem_mod.ThreeTierMemoryEngine(
        base_dir=tmp_path / "mem_store",
        cache_dir=tmp_path / "mem_cache",
        profile="argon",
    )

    def _worker(tid: int) -> int:
        count = 0
        for idx in range(5):
            ep = mem_mod.MemoryEpisode(
                episode_id=f"EP-T{tid:02d}-{idx:02d}",
                domain="ARCH",
                title=f"Concurrent Episode {tid}-{idx}",
                content=f"Payload deterministico per thread {tid} episodio {idx}.",
                tags=["concurrency", f"t{tid}"],
            )
            engine.append_episode(ep)
            count += 1
        return count

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        totals = list(pool.map(_worker, range(8)))

    assert sum(totals) == 40
    episodes = engine.get_tier2_episodes("02_Development_Patterns")
    assert len(episodes) == 40


def test_s4_01_02_ast_repo_mapper_dedent_method_calls_and_nested_classes(
    tmp_path: Path,
) -> None:
    """S4-01/02: Verifica estrazione chiamate su metodi indentati (textwrap.dedent) e ID distinti per classi annidate."""
    arm_mod = _load_staged_or_prod("ast_repo_mapper_s4", "scripts/ast_repo_mapper.py")
    pkg_dir = tmp_path / "scripts"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    sample_py = pkg_dir / "sample_nested.py"
    sample_py.write_text(
        "def helper_target() -> int:\n"
        "    return 42\n\n"
        "class OuterA:\n"
        "    class Config:\n"
        "        pass\n"
        "    def run_method(self) -> int:\n"
        "        return helper_target()\n\n"
        "class OuterB:\n"
        "    class Config:\n"
        "        pass\n",
        encoding="utf-8",
    )

    sub = arm_mod.query_symbol_subgraph("run_method", root_dir=tmp_path)
    assert sub["found"] is True
    assert "helper_target" in json.dumps(sub)

    config_sub = arm_mod.query_symbol_subgraph("Config", root_dir=tmp_path)
    assert config_sub["found"] is True
    defs = config_sub.get("definitions", config_sub.get("symbols", []))
    assert len(defs) >= 2


def test_s4_03_sast_construct_checker_blocks_dunder_import_and_binop_gaming() -> None:
    """S4-03: Verifica che SASTConstructChecker rilevi __import__, getattr(__builtins__, 'eval') e concatenazione BinOp."""
    agv_mod = _load_staged_or_prod(
        "ast_guard_s4_03", "scripts/ast_guard_validator.py"
    )
    validator = agv_mod.ASTGuardValidator()

    part_a = "PYTEST_"
    part_b = "CURRENT_TEST"
    evil_code = (
        "import os\n"
        "def exploit():\n"
        "    __import__('os').system('calc')\n"
        "    fn = getattr(__builtins__, 'eval')\n"
        f"    k = os.environ.get('{part_a}' + '{part_b}')\n"
        "    return fn, k\n"
    )
    violations = validator.check_sast_constructs(
        evil_code, target_file="scripts/app_service.py"
    )
    assert len(violations) >= 2
    symbols_and_msgs = " ".join(f"{v.symbol_name} {v.message}" for v in violations)
    assert "__import__" in symbols_and_msgs
    assert part_a in symbols_and_msgs or "SAST-GAMING" in symbols_and_msgs


def test_s6_01_03_session_bootstrap_fresh_session_isolation_and_env_capsule(
    tmp_path: Path,
) -> None:
    """S6-01/03: Verifica che un prompt utente con <env_capsule> non sia classificato come sub-agente."""
    bs_mod = _load_staged_or_prod(
        "session_bootstrap_s6", "scripts/nk_session_bootstrap.py"
    )
    user_transcript_head = json.dumps(
        {
            "source": "USER",
            "step_index": 2,
            "content": "Analizza il blocco <env_capsule> nel template",
        }
    ).encode("utf-8")
    assert (
        bs_mod.NKSessionBootstrap._is_subagent_transcript_head(user_transcript_head)
        is False
    )

    subagent_head = json.dumps(
        {
            "type": "user_input",
            "step_index": 0,
            "content": "[Message] sender=ac73aa81-7460-4b1a-8701-5849106b55d4 <env_capsule>\nWORKSPACE_ROOT: G:/Il mio Drive/Antigravity\n</env_capsule>",
        }
    ).encode("utf-8")
    assert (
        bs_mod.NKSessionBootstrap._is_subagent_transcript_head(subagent_head) is True
    )
