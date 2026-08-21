"""
Dynamic Pool Dispatcher - NK-Dynamic-Sandbox-StressTester Resource
Manages async queue with asyncio.Semaphore(2) to coordinate Phase 1 and Phase 2 executions.
"""

import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any

from phase1_surgical_runner import Phase1SurgicalRunner
from phase2_chaos_swarm_runner import Phase2RealDASTRunner


class DynamicPoolDispatcher:
    def __init__(self, workspace_root: Path, max_concurrency_p1: int = 2):
        self.workspace_root = workspace_root.resolve()
        self.semaphore_p1 = asyncio.Semaphore(max_concurrency_p1)
        self.p1_runner = Phase1SurgicalRunner(self.workspace_root)

    async def execute_phase1_bounded(self, file_path: str) -> Dict[str, Any]:
        """Executes Phase 1 surgical test on a single file wrapped in concurrency semaphore."""
        async with self.semaphore_p1:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(
                None, self.p1_runner.execute_phase1, [file_path]
            )
            return res

    async def run_full_pipeline(
        self,
        target_files: List[str],
        chaos_clone_count: int = 4,
        chaos_duration: float = 1.0
    ) -> Dict[str, Any]:
        """
        Coordinates full Dual-Mode dynamic testing:
        1. Phase 1: Parallel surgical tests bounded by semaphore(2).
        2. Phase 2: If Phase 1 passes, triggers Phase 2 Chaos Swarm on Master Sandbox.
        """
        start_time = time.time()
        
        # Step 1: Execute Phase 1 bounded tasks
        p1_tasks = [self.execute_phase1_bounded(f) for f in target_files]
        p1_results = await asyncio.gather(*p1_tasks)

        p1_failed_files: List[str] = []
        for r in p1_results:
            if r.get("failed", 0) > 0:
                for sub_r in r.get("results", []):
                    if sub_r.get("status") != "PASS":
                        p1_failed_files.append(sub_r.get("original_path", sub_r.get("file")))

        p1_passed = len(p1_failed_files) == 0

        pipeline_result: Dict[str, Any] = {
            "status": "SUCCESS" if p1_passed else "PHASE_1_FAILED",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_targets": len(target_files),
            "phase1_passed": p1_passed,
            "phase1_failures": p1_failed_files,
            "phase1_details": p1_results,
            "phase2_executed": False,
            "phase2_details": None
        }

        # Step 2: If Phase 1 succeeded, trigger Phase 2 Chaos Swarm
        if p1_passed:
            master_sandbox = Path(tempfile.gettempdir()) / f"shadow_sandbox_master_{uuid.uuid4()}"
            p2_runner = Phase2RealDASTRunner(master_sandbox, chaos_clone_count)
            p2_res = await p2_runner.run_real_dast(chaos_duration, auto_cleanup=True)
            
            pipeline_result["phase2_executed"] = True
            pipeline_result["phase2_details"] = p2_res
            if p2_res.get("status") != "PASSED":
                pipeline_result["status"] = "PHASE_2_WARNING"

        pipeline_result["total_elapsed_seconds"] = round(time.time() - start_time, 3)
        return pipeline_result


def run_pipeline_sync(
    workspace_root: Path,
    target_files: List[str],
    chaos_clone_count: int = 4,
    chaos_duration: float = 1.0
) -> Dict[str, Any]:
    """Synchronous entry point for Dynamic Pool Dispatcher."""
    dispatcher = DynamicPoolDispatcher(workspace_root)
    return asyncio.run(dispatcher.run_full_pipeline(target_files, chaos_clone_count, chaos_duration))


if __name__ == "__main__":
    import sys
    targets = sys.argv[1:] if len(sys.argv) > 1 else [__file__]
    res = run_pipeline_sync(Path("."), targets)
    print(json.dumps(res, indent=2))
