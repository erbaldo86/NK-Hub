import os
import sys
import time
import json
import asyncio
import tempfile
import contextlib

# Reconfigure stdout/stderr to UTF-8 for Windows console emoji support
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import pytest
except ImportError:
    pytest = None

@contextlib.contextmanager
def raises(expected_exception):
    try:
        yield
    except expected_exception:
        pass
    else:
        raise AssertionError(f"Expected exception {expected_exception} was not raised")

def assert_raises(exc_type, func, *args, **kwargs):
    with raises(exc_type):
        func(*args, **kwargs)

from pydantic import ValidationError

from ipc_engine import (
    pid_exists,
    LockTimeoutError,
    ProcessSafeFileLock,
    ErrorSchema,
    IPCContractPayload,
    TransactionalStateStore
)
from change_router import (
    GraphValidationError,
    CycleDetectedError,
    ChangeRouterValidator,
    DependencyGraph,
    AsyncNonBlockingOrchestrator
)
from safe_parser import (
    StructuralAnchorModel,
    safe_extract_latent_memory
)
from run_hub import NKMasterHubOrchestrator

# -------------------------------------------------------------
# Test IPC Engine and Process Lock
# -------------------------------------------------------------
def test_pid_exists():
    pid = os.getpid()
    assert pid_exists(pid) is True
    assert pid_exists(999999) is False

def test_process_safe_file_lock():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        lock_file = tmp.name + ".lock"
    
    try:
        lock = ProcessSafeFileLock(lock_file, timeout_seconds=2, lease_seconds=10)
        assert lock.acquire() is True
        
        # Test double acquire by same process (fails because lock file exists and is not orphan)
        lock2 = ProcessSafeFileLock(lock_file, timeout_seconds=1, lease_seconds=10)
        with raises(LockTimeoutError):
            lock2.acquire()
            
        lock.release()
        assert os.path.exists(lock_file) is False
    finally:
        if os.path.exists(lock_file):
            os.remove(lock_file)

def test_process_safe_file_lock_orphan():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        lock_file = tmp.name + ".lock"
        
    try:
        # Create a fake lock from an inactive PID / expired lease
        with open(lock_file, 'w', encoding='utf-8') as f:
            json.dump({
                "pid": 999999,
                "uuid": "proc-orphan-123",
                "timestamp": time.time() - 60
            }, f)
            
        lock = ProcessSafeFileLock(lock_file, timeout_seconds=2, lease_seconds=10)
        assert lock.acquire() is True
        lock.release()
    finally:
        if os.path.exists(lock_file):
            os.remove(lock_file)

def test_ipc_payload_nesting_validator():
    # Nested payload 2 levels (OK)
    payload = IPCContractPayload(
        sender="A",
        recipient="B",
        action="TEST",
        payload_data={"level1": {"level2": "val"}}
    )
    assert payload.sender == "A"
    
    # Nested payload 4 levels (fails validator)
    with raises(ValidationError):
        IPCContractPayload(
            sender="A",
            recipient="B",
            action="TEST",
            payload_data={"level1": {"level2": {"level3": {"level4": "val"}}}}
        )

# -------------------------------------------------------------
# Test Change Router & Kahn's Algorithm
# -------------------------------------------------------------
def test_change_router_cycle_detection():
    cycle_graph = {
        "A": ["B"],
        "B": ["C"],
        "C": ["A"]
    }
    with raises(GraphValidationError):
        ChangeRouterValidator.validate_and_sort(cycle_graph)

def test_change_router_depth_limit():
    deep_graph = {}
    for i in range(60):
        deep_graph[f"Node_{i}"] = [f"Node_{i+1}"]
    with raises(GraphValidationError):
        ChangeRouterValidator.validate_and_sort(deep_graph)

def test_change_router_valid_sort():
    valid_graph = {
        "NK-App-UX-Architect": ["NK-Backend-Architect"],
        "NK-Backend-Architect": ["NK-Agent-Instruction-Forge"],
        "NK-Agent-Instruction-Forge": []
    }
    order = ChangeRouterValidator.validate_and_sort(valid_graph)
    assert order == ["NK-App-UX-Architect", "NK-Backend-Architect", "NK-Agent-Instruction-Forge"]

# -------------------------------------------------------------
# Test Safe Parser (llm_structural_anchor extraction)
# -------------------------------------------------------------
def test_safe_parser():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode='w', encoding='utf-8') as tmp:
        tmp.write("""# Test Doc
Some content here.

<llm_structural_anchor>
{
  "version": "v1.0.0",
  "project_name": "TestProj",
  "nodes_dependency": {
    "A": ["B"],
    "B": []
  },
  "metadata": {}
}
</llm_structural_anchor>
""")
        tmp_filepath = tmp.name
        
    try:
        data = safe_extract_latent_memory(tmp_filepath)
        assert data["project_name"] == "TestProj"
        assert data["nodes_dependency"]["A"] == ["B"]
    finally:
        if os.path.exists(tmp_filepath):
            os.remove(tmp_filepath)

# -------------------------------------------------------------
# Test Orchestrator End-to-End behavior & NK-Python-Async-Builder features
# -------------------------------------------------------------
def test_orchestrator_flow():
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = os.path.join(tmpdir, "index.yaml")
        tree_file = os.path.join(tmpdir, "structural_tree.md")
        heartbeat_dir = os.path.join(tmpdir, "scratch", "heartbeats")
        backups_dir = os.path.join(tmpdir, "scratch", "backups")
        
        orchestrator = NKMasterHubOrchestrator(
            workspace_root=tmpdir,
            state_filepath=state_file,
            structural_tree_path=tree_file,
            heartbeat_dir=heartbeat_dir,
            backups_dir=backups_dir,
            is_autopilot=True
        )
        
        # 1. Test bootstrap initializes files & session_config
        orchestrator._create_default_structural_tree()
        state = asyncio.run(orchestrator.bootstrap(anchor_path=tree_file))
        assert os.path.exists(state_file)
        assert os.path.exists(tree_file)
        assert state["project_metadata"]["project_name"] == "NK-Master-Hub"
        assert len(state["nodi_registrati"]) == 3
        assert "session_config" in state
        assert state["session_config"]["is_autopilot"] is True
        
        # 2. Test fonti directory auto-creation
        fonti_dir = orchestrator.ensure_fonti_directory()
        assert os.path.exists(fonti_dir)
        assert os.path.exists(os.path.join(fonti_dir, "README.md"))
        
        # 3. Test orphan lock cleanup
        fake_lock = os.path.join(heartbeat_dir, "test_orphan.lock")
        os.makedirs(heartbeat_dir, exist_ok=True)
        with open(fake_lock, "w", encoding="utf-8") as f:
            json.dump({"pid": 999999, "timestamp": time.time() - 100}, f)
        asyncio.run(orchestrator.cleanup_orphan_locks())
        assert not os.path.exists(fake_lock)

        # 4. Test classify_change
        assert orchestrator.classify_change("Aggiungi una homepage L3") == "L3"
        assert orchestrator.classify_change("Modifica le dipendenze L2") == "L2"
        assert orchestrator.classify_change("Ottimizza il codice L1") == "L1"
        
        # 5. Test preservation lock
        with open(tree_file, 'r', encoding='utf-8') as f:
            content = f.read()
        locked_content = content.replace("- NK-Agent-Instruction-Forge: Unified Instruction Forge L1", "- NK-Agent-Instruction-Forge: Unified Instruction Forge L1 # [LOCK]")
        with open(tree_file, 'w', encoding='utf-8') as f:
            f.write(locked_content)
            
        assert orchestrator.is_node_locked("NK-Agent-Instruction-Forge") is True
        assert orchestrator.is_node_locked("NK-Backend-Architect") is False
        
        # Verify handle_preservation_lock creates a .new file for locked node
        target_path = os.path.join(tmpdir, "outputs", "NK-Agent-Instruction-Forge_output.md")
        orchestrator.handle_preservation_lock("NK-Agent-Instruction-Forge", target_path, "New Content")
        assert os.path.exists(target_path + ".new")
        assert not os.path.exists(target_path)
        
        # Verify handle_preservation_lock writes standard file for unlocked node
        target_path_unlocked = os.path.join(tmpdir, "outputs", "NK-Backend-Architect_output.md")
        orchestrator.handle_preservation_lock("NK-Backend-Architect", target_path_unlocked, "New Content")
        assert os.path.exists(target_path_unlocked)
        
        # 6. Test Change Router propagation (process_change)
        success = orchestrator.process_change("Modifica l'agente NK-Backend-Architect e aggiorna le dipendenze")
        assert success is True
        
        final_state = orchestrator.state_store.load_state()
        for node_info in final_state["nodi_registrati"]:
            if node_info["node_id"] in ["NK-Backend-Architect", "NK-Agent-Instruction-Forge"]:
                assert node_info["status"] == "COMPLETED"

if __name__ == "__main__":
    test_pid_exists()
    test_process_safe_file_lock()
    test_process_safe_file_lock_orphan()
    test_ipc_payload_nesting_validator()
    test_change_router_cycle_detection()
    test_change_router_depth_limit()
    test_change_router_valid_sort()
    test_safe_parser()
    test_orchestrator_flow()
    print("ALL TESTS PASSED SUCCESSFULLY!")
