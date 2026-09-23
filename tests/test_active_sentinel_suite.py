import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tempfile
import json
import time
import subprocess
import pytest

from scripts.nk_active_runtime_sentinel import run_sentinel
from scripts.nk_swarm_messenger import process_payload

def test_active_runtime_sentinel_states():
    with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:
        for _ in range(30):
            f.write('{"step": 1}\n')
        f30 = f.name
        
    with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:
        for _ in range(70):
            f.write('{"step": 1}\n')
        f70 = f.name
        
    with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:
        for _ in range(90):
            f.write('{"step": 1}\n')
        f90 = f.name
        
    with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8') as f:
        for _ in range(110):
            f.write('{"step": 1}\n')
        f110 = f.name

    t0 = time.time()
    r30 = run_sentinel(f30)
    t1 = time.time()
    assert r30['state'] == 'GREEN'
    assert (t1 - t0) < 0.05
    
    r70 = run_sentinel(f70)
    assert r70['state'] == 'CAUTION'
    
    r90 = run_sentinel(f90)
    assert r90['state'] == 'CRITICAL'
    
    r110 = run_sentinel(f110)
    assert r110['state'] == 'RED'

    os.remove(f30)
    os.remove(f70)
    os.remove(f90)
    os.remove(f110)

def _resolve_script(script_name: str) -> str:
    for candidate in [Path(".staging/scripts") / script_name, Path("scripts") / script_name]:
        if candidate.exists():
            return str(candidate)
    return str(Path("scripts") / script_name)

def test_session_handoff_capsule_and_stash(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("line1\nline2\n", encoding="utf-8")
    
    output_dir = tmp_path / "handoff"
    
    env = os.environ.copy()
    script = _resolve_script("nk_session_handoff.py")
    subprocess.run([sys.executable, script, "--transcript", str(transcript), "--output-dir", str(output_dir), "--generate-prompt"], env=env, check=True)
    
    assert (output_dir / "session_handoff_latest.json").exists()
    assert (output_dir / "next_session_prompt.md").exists()
    
    with open(output_dir / "session_handoff_latest.json", encoding="utf-8") as f:
        data = json.load(f)
        assert data["steps"] == 2
        
def test_swarm_messenger_mtu_spillover():
    p_small = "x" * 1000
    res1 = process_payload(p_small)
    assert len(res1) == 1000
    
    p_large = "x" * 5000
    res2 = process_payload(p_large)
    assert len(res2) < 1800
    assert "FULL PAYLOAD SAVED TO" in res2

def test_auto_inning_monotonic_ratchet(tmp_path):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("line1\n", encoding="utf-8")
    
    env = os.environ.copy()
    script = _resolve_script("nk_auto_inning.py")
    tuning_file = tmp_path / "tuning" / "session_tuning_params.json"
    subprocess.run([sys.executable, script, "--transcript", str(transcript), "--close-inning", "--tuning-file", str(tuning_file)], env=env, check=True)
    
    assert tuning_file.exists()
    with open(tuning_file, encoding="utf-8") as f:
        data = json.load(f)
        assert "compliance_score" in data
