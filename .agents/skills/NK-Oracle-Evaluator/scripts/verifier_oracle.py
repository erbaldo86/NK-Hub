import os
import sys
import hashlib
import json
import time
import subprocess
import psutil

class VerifierOracleEngine:
    """
    Engine di verifica deterministica per il Protocollo CRV 2.0.
    Esegue test in Shadow Sandbox, gestisce File Locking e calcola l'hash SHA-256 anti-oscillazione.
    """
    def __init__(self, target_dir, timeout_ast=10, timeout_dom=20):
        self.target_dir = target_dir
        self.timeout_ast = timeout_ast
        self.timeout_dom = timeout_dom
        self.history_hashes = set()
        self.lock_file = os.path.join(target_dir, ".memory_lock")

    def compute_patch_hash(self, patch_content: str) -> str:
        return hashlib.sha256(patch_content.encode('utf-8')).hexdigest()

    def check_oscillation(self, patch_hash: str) -> bool:
        if patch_hash in self.history_hashes:
            return True
        self.history_hashes.add(patch_hash)
        return False

    def acquire_lock(self):
        start_time = time.time()
        while os.path.exists(self.lock_file):
            if time.time() - start_time > 15:
                # Lock stantio, force remove
                try:
                    os.remove(self.lock_file)
                except OSError:
                    pass
                break
            time.sleep(0.2)
        with open(self.lock_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))

    def release_lock(self):
        if os.path.exists(self.lock_file):
            try:
                os.remove(self.lock_file)
            except OSError:
                pass

    def run_sandbox_ast_check(self, file_path: str) -> dict:
        """Esegue ast.parse su file Python per verificare che non ci siano SyntaxError."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            compile(code, file_path, 'exec')
            return {"status": "SUCCESS", "exit_code": 0, "error": None}
        except SyntaxError as se:
            return {"status": "FAIL", "exit_code": 1, "error": f"SyntaxError at line {se.lineno}: {se.msg}"}
        except Exception as e:
            return {"status": "FAIL", "exit_code": 1, "error": str(e)}

    def run_bounded_process(self, cmd: list, timeout: int) -> dict:
        """Esegue un processo figlio con kill processuale ricorsivo psutil in caso di timeout."""
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                return {"exit_code": proc.returncode, "stdout": stdout, "stderr": stderr}
            except subprocess.TimeoutExpired:
                # Kill ricorsivo dell'albero dei processi (previene Chrome/Node zombies)
                parent = psutil.Process(proc.pid)
                for child in parent.children(recursive=True):
                    child.kill()
                parent.kill()
                return {"exit_code": -1, "stdout": "", "stderr": f"TIMEOUT_EXPIRED ({timeout}s)"}
        except Exception as e:
            return {"exit_code": -2, "stdout": "", "stderr": str(e)}

if __name__ == "__main__":
    print("[NK-Oracle-Evaluator] Verifier Oracle Engine Loaded Successfully.")
