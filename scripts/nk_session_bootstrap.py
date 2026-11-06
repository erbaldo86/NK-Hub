#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Session Bootstrap Gate Fast-Stat per Nexus Keystone v3.2.0.
Modulo: nk_session_bootstrap.py.
Implementa le regole [RULE-00.4] e [RULE-PROJECT-ISOLATION] con ottimizzazioni OPT-1 e OPT-8.

Funzionalita principali:
1. Verifica invarianti Fast-Stat in meno di 25 millisecondi su cache hit.
2. Carica la cache una sola volta per ciclo con controllo TTL e conversationId.
3. Controlla l'igiene della radice tramite root_mtime e os.scandir.
4. Conta esattamente le righe del transcript attivo a blocchi binari da 64 KB.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"

_scripts_dir = Path(__file__).resolve().parent
if _scripts_dir.parent.name == ".staging":
    _workspace_root = _scripts_dir.parent.parent
else:
    _workspace_root = _scripts_dir.parent

if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

def reconfigure_streams() -> None:
    """Riconfigura gli stream standard in UTF-8 senza importare moduli esterni su cold start."""
    for _stream_name in ("stdout", "stderr"):
        _st = getattr(sys, _stream_name, None)
        if _st is not None and hasattr(_st, "reconfigure"):
            try:
                _st.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


NKContextSentry: Any = None


def _get_context_sentry() -> Any:
    """Importa in modo lazy NKContextSentry solo quando la cache non copre il transcript."""
    global NKContextSentry
    if NKContextSentry is None:
        try:
            from nk_context_sentry import NKContextSentry as _NKCS

            NKContextSentry = _NKCS
        except ImportError:
            try:
                from scripts.nk_context_sentry import NKContextSentry as _NKCS

                NKContextSentry = _NKCS
            except ImportError:
                pass
    return NKContextSentry


FAST_CACHE_TTL_SECONDS: float = 60.0
STATE_CACHE_TTL_SECONDS: float = 900.0
TRANSCRIPT_MAX_AGE_SECONDS: float = 1800.0
TAIL_READ_BYTES_LIMIT: int = 32768
BINARY_CHUNK_SIZE: int = 65536
MAX_EXACT_COUNT_BYTES: int = 50 * 1024 * 1024
_BOOTSTRAP_LOCK = threading.Lock()

_WAIT_OBJECT_0 = 0x00000000
_WAIT_ABANDONED_0 = 0x00000080
HUB_ROOT: Path = _workspace_root.resolve()


class NKSessionBootstrap:
    """Cancello deterministico di avvio sessione con verifica Fast-Stat ottimizzata."""

    _MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        workspace_root: Optional[Path] = None,
        conversation_id: Optional[str] = None,
        transcript_path: Optional[Path] = None,
    ):
        os.environ["PYTHONUTF8"] = "1"
        os.environ["PYTHONIOENCODING"] = "utf-8"
        reconfigure_streams()
        self.repo_root = (
            workspace_root.resolve()
            if workspace_root
            else Path(__file__).resolve().parent.parent
        )
        self.workspace_root = (
            Path(workspace_root).resolve() if workspace_root else _workspace_root
        )
        raw_conv_id = (
            conversation_id or os.environ.get("NK_CONVERSATION_ID", "")
        ).strip()
        self.conversation_id = raw_conv_id or self._infer_active_conversation_id(60.0)
        self.explicit_transcript_path = (
            Path(transcript_path).resolve() if transcript_path else None
        )
        self.temp_bootstrap_dir = Path(tempfile.gettempdir()) / "nk_bootstrap"
        self.state_file = self.temp_bootstrap_dir / "session_bootstrap_state.json"
        self.fast_cache_file = self.temp_bootstrap_dir / ".bootstrap_fast_cache.json"
        self.temp_bootstrap_dir.mkdir(parents=True, exist_ok=True)
        self.model_profile = os.environ.get("NK_MODEL_PROFILE", "argon")
        self._last_root_mtime: float = 0.0
        self._last_root_violations: List[str] = []

    @staticmethod
    def _get_hooks_temp_dir() -> Path:
        """Restituisce la directory temporanea degli hook runtime."""
        env_dir = os.environ.get("NK_HOOKS_TEMP_DIR")
        if env_dir:
            return Path(env_dir)
        return Path(tempfile.gettempdir()) / "nk_hooks"

    @classmethod
    def _infer_active_conversation_id(cls, max_age_seconds: float = 60.0) -> str:
        """Deduce il conversation_id dai file probe o integrity modificati di recente."""
        hooks_dir = cls._get_hooks_temp_dir()
        if not hooks_dir.exists():
            return ""
        now = time.time()
        best_conv = ""
        best_mtime = -1.0
        try:
            with os.scandir(hooks_dir) as it:
                for entry in it:
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    fname = entry.name
                    cid = ""
                    if fname.startswith("probe_") and fname.endswith(".jsonl"):
                        cid = fname[len("probe_") : -len(".jsonl")].strip()
                    elif fname.endswith("_integrity.json"):
                        cid = fname[: -len("_integrity.json")].strip()
                    if not cid or cid == "default":
                        continue
                    try:
                        mtime = entry.stat().st_mtime
                        if (now - mtime) <= max_age_seconds and mtime > best_mtime:
                            best_mtime = mtime
                            best_conv = cid
                    except Exception:
                        continue
        except Exception:
            return ""
        return best_conv

    @staticmethod
    def _is_subagent_transcript_head(head_bytes: bytes) -> bool:
        """Restituisce True solo se il primo record del transcript appartiene a un sub-agente."""
        if not head_bytes:
            return False
        first_line = head_bytes.splitlines()[0].strip()
        if not first_line:
            return False
        try:
            rec = json.loads(first_line.decode("utf-8", errors="replace"))
            if isinstance(rec, dict):
                src = str(rec.get("source", rec.get("role", ""))).strip().upper()
                if src == "USER":
                    return False
                if src == "SYSTEM":
                    return True
                text_dump = json.dumps(rec, ensure_ascii=False)
                return (
                    "[Message]" in text_dump
                    and "sender=" in text_dump
                    and "<env_capsule>" in text_dump
                )
        except Exception:
            pass
        text_head = first_line.decode("utf-8", errors="replace")
        if '"source": "USER"' in text_head or '"source":"USER"' in text_head:
            return False
        if '"source": "SYSTEM"' in text_head or '"source":"SYSTEM"' in text_head:
            return True
        return (
            "[Message]" in text_head
            and "sender=" in text_head
            and "<env_capsule>" in text_head
        )

    @staticmethod
    def _has_newer_brain_directory(cand_tp: Path, recent_window_sec: float = 60.0) -> bool:
        """Verifica se in brain/ esiste una directory conversazione piu recente del transcript in cache."""
        try:
            cand_mtime = cand_tp.stat().st_mtime
            conv_dir = cand_tp.parents[2] if len(cand_tp.parents) >= 3 else cand_tp.parent
            brain_dir = conv_dir.parent
            if not brain_dir.exists():
                return False
            now = time.time()
            with os.scandir(brain_dir) as it:
                for entry in it:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name == conv_dir.name:
                        continue
                    try:
                        st = entry.stat()
                        dir_ts = max(getattr(st, "st_ctime", 0.0), st.st_mtime)
                        if (now - dir_ts) <= recent_window_sec and dir_ts > cand_mtime:
                            return True
                    except Exception:
                        continue
        except Exception:
            return False
        return False

    def _get_root_mtime(self) -> float:
        """Restituisce il timestamp di modifica della directory radice del workspace."""
        try:
            return self.workspace_root.stat().st_mtime
        except Exception:
            return 0.0

    def _is_cache_entry_valid(self, data: Dict[str, Any], ws_key: str) -> bool:
        """Verifica che il record in cache rispetti workspace, TTL e conversation_id."""
        cached_ws = data.get("workspace_root")
        if cached_ws is not None and cached_ws != ws_key:
            return False
        now = time.time()
        cached_time = float(data.get("timestamp_epoch", 0.0))
        if cached_time <= 0.0 or (now - cached_time) > STATE_CACHE_TTL_SECONDS:
            return False
        cached_conv = str(data.get("conversation_id", "")).strip()
        if self.conversation_id and cached_conv and cached_conv != self.conversation_id:
            return False
        return True

    def _load_fast_cache(self) -> Optional[Dict[str, Any]]:
        """Carica la cache veloce una sola volta dal disco locale temporaneo o memoria."""
        ws_key = str(self.workspace_root)
        with _BOOTSTRAP_LOCK:
            for candidate in (self.fast_cache_file, self.state_file):
                if candidate.exists():
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        if isinstance(data, dict) and self._is_cache_entry_valid(
                            data, ws_key
                        ):
                            self._MEMORY_CACHE[ws_key] = data
                            return data
                    except Exception:
                        continue
            mem_entry = self._MEMORY_CACHE.get(ws_key)
            if isinstance(mem_entry, dict) and self._is_cache_entry_valid(
                mem_entry, ws_key
            ):
                return mem_entry
            return None

    def _verify_meta_prompt_gate_state(self) -> Dict[str, Any]:
        """Verifica lo stato del cancello universale Meta-Prompt (RULE-00.6)."""
        mode = os.environ.get("NK_META_PROMPT_GATE_MODE", "CONFIRM").strip().upper()
        if mode not in ("CONFIRM", "ECHO", "OFF"):
            mode = "CONFIRM"
        enabled = mode != "OFF"
        return {
            "passed": True,
            "enabled": enabled,
            "mode": mode,
            "details": f"Universal Meta-Prompt Gate active ({mode}).",
        }

    def run_bootstrap(self, fast_stat: bool = True) -> Dict[str, Any]:
        """Esegue la verifica di avvio caricando la cache una sola volta (OPT-8)."""
        start_time = time.perf_counter()
        os.environ["PYTHONUTF8"] = "1"
        os.environ["PYTHONIOENCODING"] = "utf-8"

        report: Dict[str, Any] = {
            "status": "PASS",
            "session_id": f"NK-BOOT-{int(time.time())}",
            "conversation_id": self.conversation_id,
            "model_profile": self.model_profile,
            "pythonutf8": os.environ.get("PYTHONUTF8", "1"),
            "fast_stat": fast_stat,
            "checks": {},
            "issues": [],
        }

        cached_state = self._load_fast_cache() if fast_stat else None

        # 1. Verifica immediata Fast-Pass (< 25 ms) riusando cached_state (OPT-8)
        if fast_stat and self._can_fast_pass(cached=cached_state):
            isolation_check = self._check_root_hygiene(
                use_fast_cache=True, cached=cached_state
            )
            report["checks"]["project_isolation"] = isolation_check
            if isolation_check["passed"]:
                context_check = self._verify_context_sentry(
                    use_fast_cache=True, cached=cached_state
                )
                report["checks"]["fast_stat"] = {
                    "status": "PASS",
                    "details": "Fast-stat invariant verified. TTL valid (<60s).",
                }
                report["checks"]["context_sentry"] = context_check
                report["checks"]["meta_prompt_gate"] = (
                    self._verify_meta_prompt_gate_state()
                )
                if context_check.get("warning"):
                    report["issues"].append(context_check["warning"])
                duration_ms = (time.perf_counter() - start_time) * 1000
                report["duration_ms"] = round(duration_ms, 2)
                report["execution_time_ms"] = round(duration_ms, 2)
                with _BOOTSTRAP_LOCK:
                    mem_entry = self._MEMORY_CACHE.get(str(self.workspace_root))
                    if isinstance(mem_entry, dict):
                        mem_entry["duration_ms"] = report["duration_ms"]
                        mem_entry["execution_time_ms"] = report["execution_time_ms"]
                return report

        # 2. Controlla l'igiene della radice con scansione diretta os.scandir
        isolation_check = self._check_root_hygiene(use_fast_cache=False)
        report["checks"]["project_isolation"] = isolation_check
        if not isolation_check["passed"]:
            report["status"] = "FAIL"
            report["issues"].append(isolation_check["details"])

        # 3. Bonifica i file WAL orfani con TTL > 60 secondi sotto mutex Win32 2PC
        wal_purge_check = self._purge_stale_wal_files(ttl_seconds=60.0)
        report["checks"]["wal_hygiene"] = wal_purge_check
        now_orphan_ts = time.time()
        for _pat in ("*.tmp", "*.bak"):
            for _orphan in self.repo_root.glob(_pat):
                try:
                    if _orphan.is_file() and (now_orphan_ts - _orphan.stat().st_mtime) > 60.0:
                        _orphan.unlink(missing_ok=True)
                except Exception:
                    pass

        # 4. Verifica la coerenza di quality_baseline.json
        baseline_check = self._verify_baseline()
        report["checks"]["quality_baseline"] = baseline_check
        if not baseline_check["passed"]:
            report["status"] = "FAIL"
            report["issues"].append(baseline_check["details"])

        # 5. Esegue il controllo non bloccante del Context Sentry
        context_check = self._verify_context_sentry(
            use_fast_cache=fast_stat, cached=cached_state
        )
        report["checks"]["context_sentry"] = context_check
        report["checks"]["meta_prompt_gate"] = self._verify_meta_prompt_gate_state()
        if context_check.get("warning"):
            report["issues"].append(context_check["warning"])

        duration_ms = (time.perf_counter() - start_time) * 1000
        report["duration_ms"] = round(duration_ms, 2)
        report["execution_time_ms"] = round(duration_ms, 2)
        self._save_state(report)
        return report

    def _can_fast_pass(self, cached: Optional[Dict[str, Any]] = None) -> bool:
        """Verifica se la cache rapida (<60s), root_mtime e transcript sono validi."""
        if cached is None:
            cached = self._load_fast_cache()
        if not cached:
            return False
        try:
            now = time.time()
            cached_time = float(cached.get("timestamp_epoch", 0.0))
            if (
                cached_time <= 0.0
                or (now - cached_time) > FAST_CACHE_TTL_SECONDS
                or (now - cached_time) > STATE_CACHE_TTL_SECONDS
            ):
                return False

            cached_conv = str(cached.get("conversation_id", "")).strip()
            if self.conversation_id and cached_conv != self.conversation_id:
                return False

            if cached.get("status") != "PASS":
                return False

            if cached.get("root_hygiene_violations"):
                return False

            curr_root_mtime = self._get_root_mtime()
            self._last_root_mtime = curr_root_mtime
            cached_root_mtime = cached.get("root_mtime")
            if cached_root_mtime is None or curr_root_mtime != float(cached_root_mtime):
                return False

            last_tp = cached.get("last_transcript_path", "")
            if last_tp:
                tp = Path(last_tp)
                if tp.exists():
                    t_stat = tp.stat()
                    if (now - t_stat.st_mtime) > TRANSCRIPT_MAX_AGE_SECONDS:
                        return False
                    t_size = t_stat.st_size
                    prev_size = int(cached.get("last_transcript_size", 0))
                    if t_size < prev_size or (t_size - prev_size) > TAIL_READ_BYTES_LIMIT:
                        return False

            return True
        except Exception:
            return False

    def _check_root_hygiene(
        self,
        use_fast_cache: bool = False,
        cached: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Verifica l'assenza di cartelle applicative o file Python estranei nella radice."""
        curr_mtime = (
            self._last_root_mtime
            if (use_fast_cache and self._last_root_mtime > 0.0)
            else self._get_root_mtime()
        )
        if use_fast_cache:
            if cached is None:
                cached = self._load_fast_cache()
            if (
                cached is not None
                and cached.get("root_mtime") == curr_mtime
                and (time.time() - float(cached.get("timestamp_epoch", 0.0)))
                <= FAST_CACHE_TTL_SECONDS
            ):
                detected_cached = list(cached.get("root_hygiene_violations", []))
                self._last_root_mtime = curr_mtime
                self._last_root_violations = detected_cached
                passed_cached = len(detected_cached) == 0
                return {
                    "passed": passed_cached,
                    "root_mtime": curr_mtime,
                    "violations": detected_cached,
                    "details": "Workspace root isolated."
                    if passed_cached
                    else f"Pollution detected in: {detected_cached}",
                }

        forbidden_dirs = ("src_app", "app", "src")
        detected_dirs: List[str] = []
        detected_py: List[str] = []
        is_hub_root = self.workspace_root.resolve() == HUB_ROOT.resolve()
        dir_check_root = self.workspace_root if is_hub_root else HUB_ROOT

        try:
            with os.scandir(dir_check_root) as it:
                for entry in it:
                    if (
                        entry.is_dir(follow_symlinks=False)
                        and entry.name in forbidden_dirs
                    ):
                        target = Path(entry.path)
                        if any(target.iterdir()):
                            detected_dirs.append(entry.name)
        except Exception:
            for fdir in forbidden_dirs:
                target = dir_check_root / fdir
                if target.exists() and any(target.iterdir()):
                    detected_dirs.append(fdir)

        try:
            with os.scandir(self.workspace_root) as it:
                for entry in it:
                    if entry.is_file(follow_symlinks=False) and entry.name.endswith(
                        ".py"
                    ):
                        if is_hub_root or entry.name not in ("conftest.py", "setup.py"):
                            detected_py.append(entry.name)
        except Exception:
            for root_py in self.workspace_root.glob("*.py"):
                if is_hub_root or root_py.name not in ("conftest.py", "setup.py"):
                    detected_py.append(root_py.name)

        ordered_dirs = [d for d in forbidden_dirs if d in detected_dirs]
        detected = ordered_dirs + sorted(detected_py)
        self._last_root_mtime = curr_mtime
        self._last_root_violations = detected

        passed = len(detected) == 0
        return {
            "passed": passed,
            "root_mtime": curr_mtime,
            "is_external_project": not is_hub_root,
            "violations": detected,
            "details": "Workspace root isolated."
            if passed
            else f"Pollution detected in: {detected}",
        }

    @staticmethod
    def _try_acquire_2pc_mutex_nonblocking() -> Optional[int]:
        """Tenta di acquisire in modo non bloccante il mutex Win32 2PC prima del purge WAL."""
        if sys.platform != "win32":
            return -1
        try:
            k32 = ctypes.windll.kernel32
            for m_name in (
                r"Global\NK_Hub_2PC_Transaction_Lock",
                r"Local\NK_Hub_2PC_Transaction_Lock",
            ):
                handle = k32.CreateMutexW(None, False, m_name)
                if handle:
                    wait_res = k32.WaitForSingleObject(handle, 0)
                    if wait_res in (_WAIT_OBJECT_0, _WAIT_ABANDONED_0):
                        return int(handle)
                    k32.CloseHandle(handle)
                    return None
        except Exception:
            return -1
        return -1

    @staticmethod
    def _release_2pc_mutex(handle: Optional[int]) -> None:
        """Rilascia e chiude l'handle del mutex Win32 2PC se acquisito."""
        if handle is None or handle <= 0 or sys.platform != "win32":
            return
        try:
            k32 = ctypes.windll.kernel32
            k32.ReleaseMutex(handle)
            k32.CloseHandle(handle)
        except Exception:
            pass

    @staticmethod
    def _is_committed_wal_file(wal_file: Path) -> bool:
        """Verifica se il file WAL contiene una transazione in stato COMMITTED da preservare."""
        try:
            raw = wal_file.read_text(encoding="utf-8", errors="replace").strip()
            if not raw:
                return False
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return str(parsed.get("state", "")).upper() == "COMMITTED"
            except Exception:
                pass
            for line in reversed(raw.splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if (
                        isinstance(rec, dict)
                        and str(rec.get("state", "")).upper() == "COMMITTED"
                    ):
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _purge_stale_wal_files(self, ttl_seconds: float = 60.0) -> Dict[str, Any]:
        """Elimina i file .wal_2pc.jsonl e .wal piu vecchi della soglia TTL sotto mutex 2PC."""
        mutex_handle = self._try_acquire_2pc_mutex_nonblocking()
        if mutex_handle is None:
            return {
                "passed": True,
                "stale_wals_purged": 0,
                "mutex_busy": True,
                "details": "2PC mutex active; WAL purge deferred.",
            }
        purged = 0
        now = time.time()
        temp_wal_root = Path(tempfile.gettempdir()) / "nk_2pc_wal"
        candidate_dirs = [
            self.workspace_root,
            self.workspace_root / ".staging",
            self.workspace_root / ".wal",
            self.workspace_root / "scripts" / ".wal",
            self.workspace_root / "nk_tracking",
            temp_wal_root,
        ]
        if temp_wal_root.exists() and temp_wal_root.is_dir():
            try:
                for sub_w in temp_wal_root.rglob("*"):
                    if sub_w.is_dir() and sub_w not in candidate_dirs:
                        candidate_dirs.append(sub_w)
            except Exception:
                pass
        try:
            for cdir in candidate_dirs:
                if cdir.exists():
                    try:
                        for pattern in ("*.wal_2pc.jsonl", "*.wal"):
                            for wal_file in cdir.glob(pattern):
                                if now - wal_file.stat().st_mtime > ttl_seconds:
                                    if self._is_committed_wal_file(wal_file):
                                        continue
                                    wal_file.unlink(missing_ok=True)
                                    purged += 1
                    except Exception:
                        pass
        finally:
            self._release_2pc_mutex(mutex_handle)
        return {"passed": True, "stale_wals_purged": purged}

    _purge_stale_wals = _purge_stale_wal_files

    def _verify_baseline(self) -> Dict[str, Any]:
        """Verifica che quality_baseline.json esista e abbia pass rate pari a 100%."""
        staging_baseline = (
            self.workspace_root / ".staging" / "nk_tracking" / "quality_baseline.json"
        )
        baseline_path = (
            staging_baseline
            if staging_baseline.exists()
            else self.workspace_root / "nk_tracking" / "quality_baseline.json"
        )
        if not baseline_path.exists():
            return {"passed": False, "details": "quality_baseline.json missing."}
        try:
            data = json.loads(baseline_path.read_text(encoding="utf-8"))
            metrics = (
                data.get("metrics", {})
                if isinstance(data.get("metrics"), dict)
                else {}
            )
            raw_pct = metrics.get("unit_tests_pass_pct")
            if isinstance(raw_pct, dict) and "value" in raw_pct:
                unit_pass = float(raw_pct["value"])
            elif isinstance(raw_pct, (int, float)):
                unit_pass = float(raw_pct)
            elif data.get("pass_rate_pct") is not None:
                unit_pass = float(data["pass_rate_pct"])
            elif data.get("pass_rate") is not None:
                unit_pass = float(data["pass_rate"])
            else:
                unit_pass = 0.0

            raw_tot = metrics.get("unit_tests_total") or metrics.get(
                "total_golden_tests"
            )
            if isinstance(raw_tot, dict) and "value" in raw_tot:
                total_tests = int(raw_tot["value"])
            elif isinstance(raw_tot, (int, float)):
                total_tests = int(raw_tot)
            else:
                total_tests = int(
                    data.get("total_tests")
                    or data.get("golden_tests_count")
                    or data.get("passed_tests")
                    or 0
                )

            passed = unit_pass >= 100.0
            return {
                "passed": passed,
                "unit_pass_pct": unit_pass,
                "total_tests": total_tests,
                "details": f"Baseline pass rate: {unit_pass}%",
            }
        except Exception as exc:
            return {"passed": False, "details": str(exc)}

    def _find_recent_transcript(
        self, brain_dir: Path, max_age_seconds: float = TRANSCRIPT_MAX_AGE_SECONDS
    ) -> Optional[Path]:
        """Individua il transcript attivo ordinando per transcript.stat().st_mtime entro 1800s."""
        if self.explicit_transcript_path and self.explicit_transcript_path.exists():
            return self.explicit_transcript_path

        if not brain_dir.exists():
            return None

        if self.conversation_id:
            conv_tp = (
                brain_dir
                / self.conversation_id
                / ".system_generated"
                / "logs"
                / "transcript.jsonl"
            )
            return conv_tp if conv_tp.exists() else None

        try:
            now = time.time()
            candidates: List[tuple[float, Path]] = []
            newest_unflushed_dir_ts: float = -1.0
            with os.scandir(brain_dir) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        cand = (
                            Path(entry.path)
                            / ".system_generated"
                            / "logs"
                            / "transcript.jsonl"
                        )
                        try:
                            if cand.exists():
                                cmtime = cand.stat().st_mtime
                                if (now - cmtime) <= max_age_seconds:
                                    candidates.append((cmtime, cand))
                            else:
                                dst = entry.stat()
                                dir_ts = max(getattr(dst, "st_ctime", 0.0), dst.st_mtime)
                                if (now - dir_ts) <= 60.0 and dir_ts > newest_unflushed_dir_ts:
                                    newest_unflushed_dir_ts = dir_ts
                        except Exception:
                            continue
            if not candidates:
                return None

            candidates.sort(key=lambda item: item[0], reverse=True)
            best_file: Optional[Path] = None
            best_mtime: float = -1.0
            fallback_file: Optional[Path] = None
            fallback_mtime: float = -1.0
            for cmtime, cand in candidates[:8]:
                try:
                    with open(cand, "rb") as f:
                        head_bytes = f.read(2048)
                    if self._is_subagent_transcript_head(head_bytes):
                        if cmtime > fallback_mtime:
                            fallback_mtime = cmtime
                            fallback_file = cand
                    else:
                        if cmtime > best_mtime:
                            best_mtime = cmtime
                            best_file = cand
                except Exception:
                    continue
            chosen_file = best_file or fallback_file
            chosen_mtime = best_mtime if best_file is not None else fallback_mtime
            if newest_unflushed_dir_ts > 0.0 and newest_unflushed_dir_ts > chosen_mtime:
                return None
            return chosen_file
        except Exception:
            return None

    @staticmethod
    def _count_lines_binary_64kb(transcript_file: Path, t_size: int) -> int:
        """Conta in modo esatto le righe con blocchi binari da 64 KB per file sotto 50 MB."""
        if t_size <= 0:
            return 0
        lines = 0
        with open(transcript_file, "rb") as bf:
            if t_size <= MAX_EXACT_COUNT_BYTES:
                while True:
                    chunk = bf.read(BINARY_CHUNK_SIZE)
                    if not chunk:
                        break
                    lines += chunk.count(b"\n")
                return max(1, lines)
            read_len = min(t_size, BINARY_CHUNK_SIZE)
            bf.seek(t_size - read_len)
            tail_chunk = bf.read(read_len)
            tail_lines = max(1, tail_chunk.count(b"\n"))
            return int(round((t_size / float(read_len)) * tail_lines))

    def _fast_tail_estimate(
        self,
        transcript_file: Path,
        t_size: int,
        cached: Optional[Dict[str, Any]],
        sentry: Any,
    ) -> Dict[str, Any]:
        """Calcola il numero esatto di step leggendo il transcript a blocchi da 64 KB."""
        prev_size = int(cached.get("last_transcript_size", 0)) if cached else 0
        prev_steps = int(cached.get("last_step_count", 0)) if cached else 0
        prev_cs = (cached.get("checks", {}).get("context_sentry", {}) if cached else {})
        prev_tokens = int(prev_cs.get("estimated_tokens", 0))

        if (
            cached is not None
            and prev_size > 0
            and prev_steps > 0
            and 0 <= (t_size - prev_size) <= BINARY_CHUNK_SIZE
            and cached.get("last_transcript_path") == str(transcript_file)
        ):
            delta_bytes = t_size - prev_size
            if delta_bytes > 0:
                with open(transcript_file, "rb") as bf:
                    bf.seek(prev_size)
                    tail_chunk = bf.read(delta_bytes)
                delta_steps = tail_chunk.count(b"\n")
                step_count = prev_steps + delta_steps
                est_tokens = prev_tokens + max(1, delta_bytes // 4)
            else:
                step_count = prev_steps
                est_tokens = prev_tokens
        else:
            step_count = self._count_lines_binary_64kb(transcript_file, t_size)
            est_tokens = max(1, t_size // 4) if t_size > 0 else 0

        return sentry.get_traffic_light_status(
            step_count, est_tokens, profile=self.model_profile
        )

    def _verify_context_sentry(
        self,
        use_fast_cache: bool = False,
        cached: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Esegue il controllo rapido sul transcript della conversazione attiva."""
        if cached is None and use_fast_cache:
            cached = self._load_fast_cache()
        transcript_file: Optional[Path] = None

        if self.explicit_transcript_path and self.explicit_transcript_path.exists():
            transcript_file = self.explicit_transcript_path
        elif (
            use_fast_cache
            and cached
            and (
                not self.conversation_id
                or cached.get("conversation_id") == self.conversation_id
            )
        ):
            cached_tp = cached.get("last_transcript_path", "")
            if cached_tp:
                cand_tp = Path(cached_tp)
                try:
                    if (
                        cand_tp.exists()
                        and (time.time() - cand_tp.stat().st_mtime)
                        <= TRANSCRIPT_MAX_AGE_SECONDS
                    ):
                        if not self.conversation_id and self._has_newer_brain_directory(cand_tp):
                            transcript_file = None
                        else:
                            transcript_file = cand_tp
                except Exception:
                    transcript_file = None

        if transcript_file is None:
            brain_dir = (
                Path(os.environ.get("USERPROFILE", ""))
                / ".gemini"
                / "antigravity"
                / "brain"
            )
            transcript_file = self._find_recent_transcript(brain_dir)

        if not transcript_file or not transcript_file.exists():
            return {
                "passed": True,
                "status": "GREEN",
                "step_count": 0,
                "estimated_tokens": 0,
                "last_transcript_path": "",
                "transcript_mtime": 0.0,
                "transcript_size": 0,
                "details": "No active transcript found. Fresh session assumed.",
            }

        try:
            t_stat = transcript_file.stat()
            t_mtime = t_stat.st_mtime
            t_size = t_stat.st_size

            if cached is not None:
                prev_t_size = int(cached.get("transcript_size", 0) or 0)
                if (
                    cached.get("last_transcript_path") == str(transcript_file)
                    and cached.get("active_profile") == self.model_profile
                ):
                    cached_cs = cached.get("checks", {}).get("context_sentry")
                    if isinstance(cached_cs, dict) and cached_cs.get("passed"):
                        if cached.get("transcript_mtime") == t_mtime and prev_t_size == t_size:
                            return cached_cs
                        if (
                            use_fast_cache
                            and prev_t_size > 0
                            and 0 <= (t_size - prev_t_size) <= TAIL_READ_BYTES_LIMIT
                            and cached_cs.get("status") == "GREEN"
                            and int(cached_cs.get("step_count", 0)) < 40
                            and int(cached_cs.get("estimated_tokens", 0)) + ((t_size - prev_t_size) // 4) < 40000
                        ):
                            fast_cs = dict(cached_cs)
                            fast_cs["transcript_mtime"] = t_mtime
                            fast_cs["transcript_size"] = t_size
                            return fast_cs

            sentry_cls = _get_context_sentry()
            if sentry_cls is None:
                return {"passed": True, "details": "NKContextSentry module unavailable, skipped."}
            sentry = sentry_cls(
                workspace_root=self.workspace_root, profile=self.model_profile
            )

            if use_fast_cache or t_size > TAIL_READ_BYTES_LIMIT:
                res = self._fast_tail_estimate(transcript_file, t_size, cached, sentry)
            else:
                res = sentry.analyze_transcript(transcript_file)

            status = res.get("status", "GREEN")
            step_count = int(res.get("step_count", 0))
            est_tokens = int(res.get("estimated_tokens", 0))
            warning = None
            if status == "YELLOW":
                warning = (
                    f"Context warning: session at {step_count} steps "
                    f"(~{est_tokens:,} tokens)."
                )
            elif status == "RED":
                warning = (
                    f"CRITICAL context saturation: session at {step_count} steps. "
                    "Execute /compact or nk_session_handoff.py."
                )

            return {
                "passed": True,
                "status": status,
                "health_status": "WARN" if status == "RED" else "PASS",
                "step_count": step_count,
                "estimated_tokens": est_tokens,
                "last_transcript_path": str(transcript_file),
                "transcript_mtime": t_mtime,
                "transcript_size": t_size,
                "active_profile": self.model_profile,
                "warning": warning,
                "details": f"Context status {status} ({step_count} steps).",
            }
        except Exception as exc:
            return {"passed": True, "details": f"Context Sentry check error: {exc}"}

    @staticmethod
    def _atomic_write_json(target_path: Path, serialized: str) -> None:
        """Scrive un file JSON in modo atomico tramite file .tmp e os.replace (OPT-8)."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.parent / (
            f".{target_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        try:
            tmp_path.write_text(serialized, encoding="utf-8")
            for _ in range(10):
                try:
                    os.replace(str(tmp_path), str(target_path))
                    return
                except PermissionError:
                    time.sleep(0.002)
            os.replace(str(tmp_path), str(target_path))
        except Exception:
            pass
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    def _save_state(self, report: Dict[str, Any]) -> None:
        """Salva atomicamente lo stato del bootstrap e la cache rapida (OPT-8)."""
        try:
            report_to_save = dict(report)
            report_to_save["timestamp_epoch"] = time.time()
            report_to_save["workspace_root"] = str(self.workspace_root)
            report_to_save["conversation_id"] = self.conversation_id
            report_to_save["active_profile"] = self.model_profile
            report_to_save["root_mtime"] = (
                self._last_root_mtime or self._get_root_mtime()
            )
            report_to_save["root_hygiene_violations"] = list(self._last_root_violations)
            report_to_save["root_hygiene"] = report.get("checks", {}).get(
                "project_isolation", {}
            )

            cs_info = report.get("checks", {}).get("context_sentry", {})
            if isinstance(cs_info, dict):
                t_path = str(cs_info.get("last_transcript_path", ""))
                t_mtime = float(cs_info.get("transcript_mtime", 0.0))
                t_size = int(cs_info.get("transcript_size", 0))
                t_steps = int(cs_info.get("step_count", 0))
                report_to_save["last_transcript_path"] = t_path
                report_to_save["last_transcript_mtime"] = t_mtime
                report_to_save["last_transcript_size"] = t_size
                report_to_save["last_step_count"] = t_steps
                report_to_save["transcript_mtime"] = t_mtime
                report_to_save["transcript_size"] = t_size

            serialized = json.dumps(report_to_save, indent=2)
            with _BOOTSTRAP_LOCK:
                self._MEMORY_CACHE[str(self.workspace_root)] = report_to_save
                self._atomic_write_json(self.fast_cache_file, serialized)
                self._atomic_write_json(self.state_file, serialized)
        except Exception:
            pass

    _persist_bootstrap_state = _save_state


def main(argv: Optional[List[str]] = None) -> int:
    """Punto di ingresso CLI per il Bootstrap Gate Fast-Stat di Nexus Keystone."""
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Nexus Keystone Fast-Stat Session Bootstrap Gate"
    )
    parser.add_argument(
        "--force-full",
        action="store_true",
        help="Ignora la cache Fast-Stat ed esegue la scansione completa",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )
    parser.add_argument(
        "--conversation-id",
        type=str,
        default=None,
        help="ID della conversazione attiva per isolare cache e transcript",
    )
    parser.add_argument(
        "--transcript",
        type=str,
        default=None,
        help="Percorso esplicito del file transcript.jsonl",
    )
    parser.add_argument(
        "--hook",
        action="store_true",
        help="Esegue il bootstrap in modalita hook SessionStart",
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Percorso radice del workspace o progetto da verificare",
    )

    args = parser.parse_args(argv)
    conv_id = args.conversation_id
    transcript_arg = args.transcript

    if args.hook and not sys.stdin.isatty():
        try:
            raw_stdin = sys.stdin.read()
            if raw_stdin.strip():
                hook_payload = json.loads(raw_stdin)
                if isinstance(hook_payload, dict):
                    conv_id = conv_id or str(
                        hook_payload.get("conversationId")
                        or hook_payload.get("conversation_id")
                        or ""
                    )
                    transcript_arg = transcript_arg or str(
                        hook_payload.get("transcriptPath")
                        or hook_payload.get("transcript_path")
                        or ""
                    )
        except Exception:
            pass

    ws_root = Path(args.project_root).resolve() if args.project_root else None
    tp_path = Path(transcript_arg).resolve() if transcript_arg else None
    bootstrap = NKSessionBootstrap(
        workspace_root=ws_root,
        conversation_id=conv_id,
        transcript_path=tp_path,
    )
    res = bootstrap.run_bootstrap(fast_stat=not args.force_full)

    if args.json or args.hook:
        print(json.dumps(res, indent=2))
    else:
        status_symbol = "🟢" if res["status"] == "PASS" else "🔴"
        print(
            f"{status_symbol} [NK-BOOTSTRAP] Status: {res['status']} | Duration: {res.get('duration_ms', 0)} ms"
        )
        for check_name, check_data in res.get("checks", {}).items():
            print(f"  - {check_name}: {check_data.get('details', check_data)}")
        for issue in res.get("issues", []):
            print(f"  ⚠️ [ALERT] {issue}")

    return 0 if res["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
