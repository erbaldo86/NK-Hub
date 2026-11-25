# -*- coding: utf-8 -*-
"""Sharding parallelo file-level su NVMe per esecuzione pytest isolata."""

from __future__ import annotations

import concurrent.futures, json, os, re, subprocess, sys, tempfile, time, xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from _internal.nk_common.staging_manifest import file_has_async_marker, filter_fast_marker_files

_SINGLE_PROC_FLAGS = frozenset({"--collect-only", "--lf", "--last-failed", "--ff", "--failed-first", "--pdb", "-x", "--exitfirst", "-s"})
_COV_SOURCE_CANDIDATES = ("scripts", "src_app", "app", "src")
_ASYNC_CFG_MARKERS = ("asyncio_mode", "pytest_asyncio", "anyio")
_FAST_PROFILE_RE = re.compile(r"(?:^|\s)fast(?:\s|$)")

def resolve_coverage_source(workspace_root: Path) -> str:
    """Risolve il pacchetto sorgente coverage distinguendo repo app esterne e NK_Hub."""
    ws = Path(workspace_root)
    if (ws / "src_app").is_dir() and not (ws / ".agents" / "skills").is_dir():
        return "src_app"
    return next((c for c in _COV_SOURCE_CANDIDATES if (ws / c).is_dir()), "scripts")

def detect_async_pytest_needed(mirror_dir: Path, test_files: Sequence[str]) -> bool:
    """Rileva configurazioni o test asyncio/anyio evitando falso positivo su test sync."""
    m_res = Path(mirror_dir)
    for cfg_name in ("pytest.ini", "pyproject.toml"):
        cfg_p = m_res / cfg_name
        if cfg_p.is_file():
            try:
                if any(tok in cfg_p.read_text(encoding="utf-8-sig", errors="ignore").lower() for tok in _ASYNC_CFG_MARKERS):
                    return True
            except OSError:
                pass
    for rel_f in test_files:
        fp = (m_res / str(rel_f)) if not Path(str(rel_f)).is_absolute() else Path(str(rel_f))
        if file_has_async_marker(fp):
            return True
    return False

def resolve_worker_count(num_files: int, env: Optional[Mapping[str, str]] = None) -> int:
    """Calcola il numero di worker pytest paralleli con override NK_PYTEST_WORKERS."""
    if num_files < 2:
        return 1
    src_env = os.environ if env is None else env
    if raw := str(src_env.get("NK_PYTEST_WORKERS", "")).strip():
        try:
            return max(1, min(12, num_files, int(raw)))
        except ValueError:
            raw = ""
    return min(10, max(2, os.cpu_count() or 4), num_files)

def _has_disqualifying_shard_args(norm_targets: Sequence[str], extra_args: Sequence[str], env_map: Mapping[str, str]) -> bool:
    """Verifica le condizioni che impongono il percorso single-process."""
    if str(env_map.get("NK_PYTEST_WORKERS", "")).strip() == "1" or any("::" in str(t) for t in norm_targets):
        return True
    return any(str(a).strip() in _SINGLE_PROC_FLAGS or str(a).strip().startswith("--maxfail") for a in extra_args)

def _expand_single_target(raw_t: str, m_res: Path) -> List[str]:
    """Espande un singolo target pytest relativo a mirror_dir escludendo __pycache__."""
    if not (text := str(raw_t).strip()):
        return []
    cand = (Path(text) if Path(text).is_absolute() else (m_res / text)).resolve()
    if not cand.is_relative_to(m_res):
        return []
    if cand.is_dir():
        return [fp.relative_to(m_res).as_posix() for fp in sorted(cand.rglob("test_*.py")) if fp.is_file() and "__pycache__" not in fp.parts]
    return [cand.relative_to(m_res).as_posix()] if (cand.is_file() and "__pycache__" not in cand.parts) else []

def should_use_parallel_shards(norm_targets: Sequence[str], extra_args: Sequence[str], mirror_dir: Path, env: Optional[Mapping[str, str]] = None) -> List[str]:
    """Restituisce i path relativi POSIX da shardare oppure [] per single-process."""
    src_env = os.environ if env is None else env
    if _has_disqualifying_shard_args(norm_targets, extra_args, src_env):
        return []
    m_res = mirror_dir.resolve()
    discovered = list(dict.fromkeys(f for raw_t in norm_targets for f in _expand_single_target(raw_t, m_res)))
    filtered = filter_fast_marker_files(discovered, _timing_profile_key(extra_args, coverage=False), m_res)
    return filtered if (len(filtered) >= 4 and resolve_worker_count(len(filtered), src_env) >= 2) else []

def _timings_cache_path() -> Path:
    """Restituisce il path cache JSON dei tempi storici shard in TEMP."""
    base = os.environ.get("TEMP", "").strip() or os.environ.get("TMP", "").strip() or tempfile.gettempdir()
    return Path(base) / "nk_diagnostics" / "pytest_shard_timings.json"

def _timing_profile_key(extra_args: Sequence[str], coverage: bool) -> str:
    """Restituisce la chiave profilo isolata per la cache dei tempi shard."""
    if coverage:
        return "cov"
    joined = " ".join(str(a).lower() for a in extra_args)
    if "not stress" in joined:
        return "t1_t2"
    if _FAST_PROFILE_RE.search(joined) and "not fast" not in joined and "or " not in joined and "and " not in joined:
        return "fast"
    return next((m for m in ("integration", "stress") if m in joined), "full")

def _normalize_timing_entries(entries: Mapping[Any, Any]) -> Dict[str, int]:
    """Filtra e converte una mappa di timing in millisecondi interi positivi."""
    return {str(k): max(1, int(v)) for k, v in entries.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}

def _read_timing_store() -> Dict[str, Any]:
    """Legge il dizionario JSON dei profili timing fallendo vuoto se assente o corrotto."""
    try:
        raw = json.loads(_timings_cache_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}

def _load_timing_weights(profile: str = "default") -> Dict[str, int]:
    """Carica i tempi storici in millisecondi isolati per profilo."""
    raw = _read_timing_store()
    scoped = raw.get(profile)
    if isinstance(scoped, dict):
        return _normalize_timing_entries(scoped)
    return _normalize_timing_entries(raw) if profile == "default" else {}

def _classname_to_rel_path(classname: str) -> Optional[str]:
    """Converte un classname JUnit in percorso relativo tests/.../test_*.py."""
    parts = [p for p in str(classname or "").strip().split(".") if p]
    for idx, seg in enumerate(parts):
        if seg.startswith("test_"):
            rel = "/".join(parts[: idx + 1]) + ".py"
            return rel if rel.startswith("tests/") else None
    return None

def _testcase_seconds(tc: ET.Element) -> float:
    """Estrae in modo sicuro l'attributo time in secondi da un elemento testcase."""
    try:
        return max(0.0, float(tc.attrib.get("time", "0") or 0))
    except (TypeError, ValueError):
        return 0.0

def _collect_suite_timings_ms(suites: Sequence[ET.Element]) -> Dict[str, int]:
    """Accumula la durata storica in ms per ogni modulo tests/... dalle suite JUnit."""
    totals_s: Dict[str, float] = {}
    for suite in suites:
        for tc in suite.iter("testcase"):
            if rel := _classname_to_rel_path(tc.attrib.get("classname", "")):
                totals_s[rel] = totals_s.get(rel, 0.0) + _testcase_seconds(tc)
    return {rel: max(1, int(round(sec * 1000.0))) for rel, sec in totals_s.items()}

def _save_timing_weights(suites: Sequence[ET.Element], profile: str = "default") -> None:
    """Aggiorna atomicamente il profilo timing in pytest_shard_timings.json."""
    if not (measured := _collect_suite_timings_ms(suites)):
        return
    cache_p, store = _timings_cache_path(), _read_timing_store()
    prev = store.get(profile)
    store[profile] = {**(prev if isinstance(prev, dict) else {}), **measured}
    tmp_p = cache_p.parent / f".timings_{os.getpid()}_{time.monotonic_ns()}.tmp"
    try:
        cache_p.parent.mkdir(parents=True, exist_ok=True)
        tmp_p.write_text(json.dumps(store, sort_keys=True), encoding="utf-8")
        os.replace(tmp_p, cache_p)
    except OSError:
        return

def _file_weight(mirror_dir: Path, rel_path: str) -> int:
    """Restituisce il peso in byte del file test con fallback 1 su OSError."""
    try:
        return max(1, int((mirror_dir / rel_path).stat().st_size))
    except OSError:
        return 1

def partition_files_lpt(test_files: Sequence[str], mirror_dir: Path, workers: int, profile: str = "default") -> List[List[str]]:
    """Partiziona i file test con LPT pesato su timing storici per profilo o fallback st_size//10."""
    if not test_files:
        return []
    w_cnt, timings = max(1, int(workers)), _load_timing_weights(profile)
    ordered = sorted((((timings.get(str(f)) or (max(1, _file_weight(mirror_dir, str(f)) // 10) if timings else _file_weight(mirror_dir, str(f)))), str(f)) for f in test_files), key=lambda item: (item[0], item[1]), reverse=True)
    loads, shards = [0] * w_cnt, [[] for _ in range(w_cnt)]
    for weight, rel_path in ordered:
        idx = min(range(w_cnt), key=lambda i: (loads[i], i))
        shards[idx].append(rel_path)
        loads[idx] += weight
    return [shard for shard in shards if shard]

def strip_junitxml_args(extra_args: Sequence[str]) -> List[str]:
    """Rimuove --junitxml=... e coppia --junitxml <path> da extra_args."""
    cleaned: List[str] = []
    skip_next = False
    for raw_arg in extra_args:
        if skip_next:
            skip_next = False
            continue
        if (arg := str(raw_arg)) == "--junitxml":
            skip_next = True
        elif not arg.startswith("--junitxml="):
            cleaned.append(arg)
    return cleaned

def _extract_suites_from_xml(xml_path: Path) -> List[ET.Element]:
    """Valida XML senza ENTITY ed estrae gli elementi testsuite."""
    txt = xml_path.read_text(encoding="utf-8-sig")
    if "<!ENTITY" in txt.upper():
        raise ValueError(f"Dichiarazione XML ENTITY non consentita: {xml_path}")
    try:
        root = ET.fromstring(txt)
    except ET.ParseError:
        return []
    if root.tag == "testsuite":
        return [root]
    return [child for child in root if child.tag == "testsuite"] if root.tag == "testsuites" else []

def _suite_int_attr(elem: ET.Element, attr: str) -> int:
    """Estrae un attributo intero non negativo da un elemento testsuite."""
    try:
        return max(0, int(elem.attrib.get(attr, "0") or 0))
    except ValueError:
        return 0

def merge_junit_xml_files(worker_xmls: Sequence[Path], dest_xml: Path, wall_duration_s: float, record_timings: bool = False, profile: str = "default") -> Optional[Path]:
    """Unisce i report JUnit XML dei worker in dest_xml registrando opzionalmente i tempi."""
    suites = [s for xml_p in worker_xmls if xml_p.is_file() for s in _extract_suites_from_xml(xml_p)]
    if not suites:
        return None
    totals = {k: str(sum(_suite_int_attr(s, k) for s in suites)) for k in ("tests", "failures", "errors", "skipped")}
    merged = ET.Element("testsuites", {**totals, "time": f"{max(0.0, float(wall_duration_s)):.3f}"})
    merged.extend(suites)
    dest_xml.parent.mkdir(parents=True, exist_ok=True)
    dest_xml.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(merged, encoding="unicode"), encoding="utf-8")
    if record_timings:
        _save_timing_weights(suites, profile)
    return dest_xml

def combine_worker_coverage(cov_parts_dir: Path, mirror_dir: Path, cov_json: Path, cov_source: Optional[str] = None) -> bool:
    """Combina i file .coverage.w* dei worker ed esporta cov_json."""
    parts = sorted(p for p in cov_parts_dir.glob(".coverage.w*") if p.is_file()) if cov_parts_dir.is_dir() else []
    if not parts:
        return False
    eff_source = cov_source or resolve_coverage_source(mirror_dir)
    try:
        import coverage
        cov_json.parent.mkdir(parents=True, exist_ok=True)
        cov = coverage.Coverage(data_file=str(cov_parts_dir / ".coverage"), source=[str(mirror_dir / eff_source)], branch=True)
        cov.combine(data_paths=[str(p) for p in parts], strict=False, keep=False)
        cov.json_report(outfile=str(cov_json))
        return cov_json.is_file()
    except Exception:
        return False

def _build_worker_command(
    shard_files: Sequence[str], w_bt: Path, w_xml: Path, clean_extra: Sequence[str], coverage: bool, w_env: Mapping[str, str],
    cov_source: str = "scripts", disable_async_plugins: bool = True,
) -> List[str]:
    """Costruisce il comando pytest isolato per un singolo worker shard."""
    imp_args = [] if any(str(a).startswith("--import-mode") for a in clean_extra) else ["--import-mode=importlib"]
    async_dis = ["-p", "no:anyio", "-p", "no:asyncio"] if disable_async_plugins else []
    cov_args = ((["-p", "pytest_cov"] if w_env.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") else []) + [f"--cov={cov_source}", "--cov-branch", "--cov-report="]) if coverage else []
    return [sys.executable, "-B", "-u", "-m", "pytest", "-p", "no:cacheprovider", *async_dis, *imp_args, f"--basetemp={w_bt.as_posix()}", f"--junitxml={w_xml.as_posix()}", *cov_args, *clean_extra, *shard_files]

def _terminate_timed_out_proc(proc: Any, kill_tree_fn: Optional[Callable[[int], None]]) -> None:
    """Termina l'albero processi di un worker scaduto senza bloccare."""
    if kill_tree_fn is not None and (pid := getattr(proc, "pid", 0) or 0):
        kill_tree_fn(int(pid))
    try:
        proc.kill()
        proc.wait(timeout=2.0)
    except (OSError, subprocess.SubprocessError, ValueError):
        return

def _run_single_worker(
    idx: int, shard_files: Sequence[str], mirror_dir: Path, mirror_root: Path, base_env: Mapping[str, str], clean_extra: Sequence[str],
    deadline: float, coverage: bool, cov_parts_dir: Optional[Path], kill_tree_fn: Optional[Callable[[int], None]], detached_flags: int,
    cov_source: str = "scripts", disable_async_plugins: bool = True,
) -> Dict[str, Any]:
    """Esegue un singolo shard pytest in directory temporanee isolate."""
    w_dir = mirror_root / f"w_{idx}"
    w_tmp, w_hooks, w_bt = w_dir / "tmp", w_dir / "hooks_tmp", w_dir / "tmp" / "bt"
    [sub.mkdir(parents=True, exist_ok=True) for sub in (w_tmp, w_hooks, w_bt)]
    cov_extra = {"COVERAGE_FILE": str(cov_parts_dir / f".coverage.w{idx}")} if (coverage and cov_parts_dir is not None) else {}
    w_env = {**base_env, "TEMP": str(w_tmp), "TMP": str(w_tmp), "TMPDIR": str(w_tmp), "NK_HOOKS_TEMP_DIR": str(w_hooks), **cov_extra}
    w_xml, w_log = w_dir / "junit.xml", w_dir / "worker.log"
    cmd = _build_worker_command(shard_files, w_bt, w_xml, clean_extra, coverage, w_env, cov_source=cov_source, disable_async_plugins=disable_async_plugins)
    timed_out, w_rc = False, 1
    try:
        with open(w_log, "w", encoding="utf-8", errors="replace") as log_fh:
            proc = subprocess.Popen(cmd, cwd=str(mirror_dir), env=w_env, stdin=subprocess.DEVNULL, stdout=log_fh, stderr=subprocess.STDOUT, creationflags=detached_flags, shell=False)
            while (polled := proc.poll()) is None:
                if time.perf_counter() >= deadline:
                    timed_out, w_rc = True, -1
                    _terminate_timed_out_proc(proc, kill_tree_fn)
                    break
                time.sleep(0.03)
            else:
                w_rc = int(polled)
    except OSError as exc:
        w_rc = 1
        w_log.write_text(f"[WORKER_ERROR] {exc}\n", encoding="utf-8", errors="replace")
    return {"idx": idx, "rc": w_rc, "timed_out": timed_out, "log": w_log.read_text(encoding="utf-8", errors="replace") if w_log.is_file() else "", "xml": w_xml}

def _aggregate_worker_outcomes(outcomes: Sequence[Dict[str, Any]]) -> Tuple[int, bool]:
    """Aggrega exit code e timeout dei worker gestendo rc=5 di shard vuoti."""
    if not outcomes:
        return 5, False
    if any(bool(o.get("timed_out")) for o in outcomes):
        return -1, True
    if non_0_5 := [int(o["rc"]) for o in outcomes if int(o["rc"]) not in (0, 5)]:
        return non_0_5[0], False
    return (5, False) if all(int(o["rc"]) == 5 for o in outcomes) else (0, False)

def _write_combined_log(outcomes: Sequence[Dict[str, Any]], log_file: Optional[Path]) -> str:
    """Unisce i log dei worker e li salva opzionalmente su log_file."""
    parts = [str(o["log"]).rstrip("\n") for o in outcomes if o.get("log")]
    combined_log = ("\n".join(parts) + "\n") if parts else ""
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.write_text(combined_log, encoding="utf-8", errors="replace")
    return combined_log

def _finalize_parallel_artifacts(
    outcomes: Sequence[Dict[str, Any]], wall_s: float, coverage: bool, timed_out: bool,
    cov_parts_dir: Optional[Path], mirror_dir: Path, cov_json: Optional[Path], junit_xml_path: Optional[Path], log_file: Optional[Path],
    profile: str = "default", cov_source: Optional[str] = None,
) -> str:
    """Consolida log combinato, JUnit XML unificato e coverage JSON."""
    combined_log = _write_combined_log(outcomes, log_file)
    if junit_xml_path is not None:
        merge_junit_xml_files([o["xml"] for o in outcomes], junit_xml_path, wall_s, record_timings=True, profile=profile)
    if coverage and not timed_out and cov_json is not None and cov_parts_dir is not None:
        combine_worker_coverage(cov_parts_dir, mirror_dir, cov_json, cov_source=cov_source)
    return combined_log

def _resolve_parallel_env(base_env: Mapping[str, str], disable_async: bool) -> Mapping[str, str]:
    return base_env if (not disable_async or "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in base_env) else {**base_env, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}

def run_parallel_pytest_shards(
    mirror_dir: Path, mirror_root: Path, test_files: Sequence[str], base_env: Mapping[str, str], extra_args: Sequence[str], timeout_sec: float,
    coverage: bool, cov_json: Optional[Path] = None, junit_xml_path: Optional[Path] = None, log_file: Optional[Path] = None,
    workers: Optional[int] = None, kill_tree_fn: Optional[Callable[[int], None]] = None, detached_flags: int = 0,
) -> Dict[str, Any]:
    """Esegue gli shard pytest in parallelo su NVMe unendo log, XML e coverage."""
    t0, deadline = time.perf_counter(), time.perf_counter() + max(0.05, float(timeout_sec))
    w_cnt = workers if (workers is not None and workers >= 1) else resolve_worker_count(len(test_files), base_env)
    clean_extra = strip_junitxml_args(extra_args)
    prof = _timing_profile_key(clean_extra, coverage)
    shards = partition_files_lpt(test_files, mirror_dir, w_cnt, profile=prof)
    cov_src, disable_async = resolve_coverage_source(mirror_dir), not detect_async_pytest_needed(mirror_dir, test_files)
    eff_env = _resolve_parallel_env(base_env, disable_async)
    cov_parts_dir = (mirror_root / "cov_parts") if coverage else None
    if cov_parts_dir is not None:
        cov_parts_dir.mkdir(parents=True, exist_ok=True)
    outcomes: List[Dict[str, Any]] = []
    if shards:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(shards)) as pool:
            futs = [pool.submit(_run_single_worker, idx, sf, mirror_dir, mirror_root, eff_env, clean_extra, deadline, coverage, cov_parts_dir, kill_tree_fn, detached_flags, cov_source=cov_src, disable_async_plugins=disable_async) for idx, sf in enumerate(shards)]
            outcomes = [fut.result() for fut in futs]
    wall_s = round(time.perf_counter() - t0, 3)
    rc, timed_out = _aggregate_worker_outcomes(outcomes)
    combined_log = _finalize_parallel_artifacts(outcomes, wall_s, coverage, timed_out, cov_parts_dir, mirror_dir, cov_json, junit_xml_path, log_file, profile=prof, cov_source=cov_src)
    return {"rc": rc, "timed_out": timed_out, "duration_s": round(time.perf_counter() - t0, 3), "log_text": combined_log, "workers_used": len(shards), "junit_xml": junit_xml_path}
