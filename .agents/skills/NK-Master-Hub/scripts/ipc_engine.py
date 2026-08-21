import os
import time
import json
import subprocess
import uuid
import yaml
import shutil
import random
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field, field_validator

# -------------------------------------------------------------
# Native PID Existence Check (No psutil required)
# -------------------------------------------------------------
def pid_exists(pid: int) -> bool:
    """Verifica se un processo con il PID specificato è attivo nel sistema operativo."""
    if os.name == 'nt':
        try:
            # Esegue tasklist per cercare il PID su Windows
            output = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8', errors='ignore')
            return str(pid) in output
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

# -------------------------------------------------------------
# Lock Exceptions & Process-Safe File Lock
# -------------------------------------------------------------
class LockTimeoutError(Exception):
    """Eccezione sollevata quando l'acquisizione del lock va in timeout."""
    pass

class ProcessSafeFileLock:
    def __init__(self, lock_filepath: str, timeout_seconds: int = 10, lease_seconds: int = 30):
        self.lock_filepath = os.path.abspath(lock_filepath)
        self.timeout_seconds = timeout_seconds
        self.lease_seconds = lease_seconds
        self.pid = os.getpid()
        self.uuid = f"proc-{self.pid}-{time.time_ns()}"
        self.acquired = False

    def acquire(self) -> bool:
        start_time = time.time()
        while time.time() - start_time < self.timeout_seconds:
            if not os.path.exists(self.lock_filepath):
                # Tenta di creare il file in modo esclusivo
                try:
                    fd = os.open(self.lock_filepath, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    with os.fdopen(fd, 'w') as f:
                        json.dump({
                            "pid": self.pid,
                            "uuid": self.uuid,
                            "timestamp": time.time()
                        }, f)
                    self.acquired = True
                    return True
                except FileExistsError:
                    pass
            
            # Se esiste, controlla se è orfano (processo morto o lease scaduto)
            try:
                with open(self.lock_filepath, 'r') as f:
                    data = json.load(f)
                
                lock_pid = data.get("pid")
                lock_ts = data.get("timestamp", 0)
                
                # Controllo se il processo proprietario è ancora in esecuzione
                process_alive = False
                if lock_pid:
                    process_alive = pid_exists(lock_pid)
                
                lease_expired = (time.time() - lock_ts) > self.lease_seconds
                
                # Se il processo è morto o il lease è scaduto, possiamo forzare il lock
                if not process_alive or lease_expired:
                    print(f"[LOCK] Rilevato lock orfano (PID alive: {process_alive}, Lease expired: {lease_expired}). Rimozione in corso...")
                    try:
                        os.remove(self.lock_filepath)
                    except OSError:
                        pass # Qualcun altro potrebbe averlo rimosso nel frattempo
            except Exception:
                # File corrotto o in scrittura, attendi la prossima iterazione
                pass
            
            # Adaptive Jitter tra 50ms e 250ms per prevenire lock contention e thundering herd
            time.sleep(random.uniform(0.05, 0.25))
        
        raise LockTimeoutError(f"Impossibile acquisire il lock entro {self.timeout_seconds} secondi.")

    def release(self):
        if not self.acquired:
            return
        try:
            with open(self.lock_filepath, 'r') as f:
                data = json.load(f)
            # Rilascia solo se il lock è effettivamente il nostro
            if data.get("uuid") == self.uuid:
                os.remove(self.lock_filepath)
                self.acquired = False
        except Exception:
            pass

# -------------------------------------------------------------
# Pydantic v2 schemas for IPC Contracts
# -------------------------------------------------------------
class ErrorSchema(BaseModel):
    code: str = Field(..., pattern=r"^ERR_[A-Z0-9_]+$")
    message: str
    fatal: bool

class IPCContractPayload(BaseModel):
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    recipient: str
    action: str
    payload_data: Dict[str, Any]
    error_schema: Optional[ErrorSchema] = None

    @field_validator("payload_data")
    @classmethod
    def validate_nesting_depth(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        def get_depth(d: Any) -> int:
            if not isinstance(d, dict):
                return 0
            if not d:
                return 1
            return 1 + max(get_depth(val) for val in d.values())
        
        depth = get_depth(v)
        if depth > 3:
            raise ValueError(f"Il payload IPC supera la profondità massima consentita di 3 livelli (Rilevato: {depth})")
        return v

# -------------------------------------------------------------
# Transactional State Store (using ProcessSafeFileLock)
# -------------------------------------------------------------
class TransactionalStateStore:
    def __init__(self, filepath: str, lock_timeout: float = 10.0, lease_seconds: int = 30):
        self.filepath = os.path.abspath(filepath)
        self.lock_filepath = self.filepath + ".lock"
        self.lock_timeout = lock_timeout
        self.lease_seconds = lease_seconds

    def load_state(self) -> Dict[str, Any]:
        lock = ProcessSafeFileLock(self.lock_filepath, timeout_seconds=int(self.lock_timeout), lease_seconds=self.lease_seconds)
        lock.acquire()
        try:
            if not os.path.exists(self.filepath):
                return {}
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data if data else {}
        finally:
            lock.release()

    def save_state(self, state: Dict[str, Any]) -> None:
        lock = ProcessSafeFileLock(self.lock_filepath, timeout_seconds=int(self.lock_timeout), lease_seconds=self.lease_seconds)
        lock.acquire()
        temp_filepath = self.filepath + f".{uuid.uuid4().hex}.tmp"
        try:
            # Scrittura atomica tramite file temporaneo e sostituzione con retry per Windows Sync
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                yaml.safe_dump(state, f, default_flow_style=False, sort_keys=False)
            
            # Sostituzione atomica protetta da backoff per Windows Cloud Sync locks
            max_retries = 5
            delays = [0.05, 0.1, 0.2, 0.4, 0.8]
            for attempt in range(max_retries):
                try:
                    if os.path.exists(self.filepath):
                        os.replace(temp_filepath, self.filepath)
                    else:
                        os.rename(temp_filepath, self.filepath)
                    break
                except PermissionError:
                    if attempt < max_retries - 1:
                        # Exponential backoff con Adaptive Jitter
                        sleep_time = delays[attempt] + random.uniform(0.01, 0.05)
                        time.sleep(sleep_time)
                    else:
                        raise
        except Exception as e:
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except OSError:
                    pass
            raise e
        finally:
            lock.release()
