"""
Peer Review Validator - NK-Security-Auditor Resource
Handles double-blind cross-clone validation of proposed patches before supervisor integration.
"""

import ast
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


def win32_backoff_write(file_path: Path, content: str, max_retries: int = 5, initial_delay: float = 0.1) -> None:
    """Writes content to file using atomic replace with Win32 Exponential Backoff."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp_" + str(time.time_ns()))
    
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
            temp_path.replace(file_path)
            return
        except (PermissionError, OSError) as e:
            if attempt == max_retries - 1:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise e
            time.sleep(delay)
            delay *= 2.0


class PeerReviewValidator:
    def __init__(self, max_healing_attempts: int = 3):
        self.max_healing_attempts = max_healing_attempts

    def validate_patch_syntax(self, code_snippet: str) -> Tuple[bool, Optional[str]]:
        """Performs AST parsing check on Python code patches."""
        if not code_snippet or not code_snippet.strip():
            return True, None  # Empty patch is harmless or non-code patch
        try:
            ast.parse(code_snippet)
            return True, None
        except SyntaxError as se:
            return False, f"SyntaxError line {se.lineno}: {se.msg}"
        except Exception as e:
            return False, f"AST Validation Error: {str(e)}"

    def execute_double_blind_review(
        self,
        reviewer_clone_id: str,
        target_clone_id: str,
        patch_payload: Dict[str, Any],
        output_ipc_dir: Path
    ) -> Dict[str, Any]:
        """
        Executes double-blind validation of a patch proposed by target_clone_id.
        Saves the validation result to peer_review_<target>_to_<reviewer>.json.
        """
        target_file = patch_payload.get("target_file", "")
        proposed_code = patch_payload.get("proposed_code", "")
        patch_description = patch_payload.get("description", "")

        # Step 1: Syntax / AST Check
        is_valid_syntax, err_msg = self.validate_patch_syntax(proposed_code)

        # Step 2: Logical / Format Verification
        is_valid_format = bool(target_file) and isinstance(patch_payload, dict)
        
        status = "PASSED" if (is_valid_syntax and is_valid_format) else "REJECTED"
        
        review_result = {
            "reviewer_clone_id": reviewer_clone_id,
            "target_clone_id": target_clone_id,
            "target_file": target_file,
            "status": status,
            "syntax_check": "SUCCESS" if is_valid_syntax else f"FAIL: {err_msg}",
            "format_check": "SUCCESS" if is_valid_format else "FAIL: Missing target_file or invalid structure",
            "feedback": err_msg if err_msg else "Patch validated successfully.",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }

        output_file = output_ipc_dir / f"peer_review_{target_clone_id}_to_{reviewer_clone_id}.json"
        win32_backoff_write(output_file, json.dumps(review_result, indent=2))

        return review_result


if __name__ == "__main__":
    import sys
    validator = PeerReviewValidator()
    sample_patch = {
        "target_file": "sample.py",
        "proposed_code": "def foo():\n    return 'hello'\n",
        "description": "Add foo function"
    }
    res = validator.execute_double_blind_review(
        reviewer_clone_id="clone_2",
        target_clone_id="clone_1",
        patch_payload=sample_patch,
        output_ipc_dir=Path("./scratch/swarm_ipc/test_session")
    )
    print(json.dumps(res, indent=2))
