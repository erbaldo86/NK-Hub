# -*- coding: utf-8 -*-
"""Scheduler a onde parallele basato su DAG di Kahn e graph-coloring per write-set M4."""

from __future__ import annotations

from typing import Collection, Dict, List, Optional, Sequence, Set, Tuple
from pydantic import BaseModel, ConfigDict, Field

from _internal.nk_common.lane_paths import validate_lane_id
from schemas.dual_ledgers_models import TaskDAGNode

WriteKey = Tuple[str, str]


class WaveTaskAssignment(BaseModel):
    """Assegnazione di un task ad una wave parallela con write-set normalizzato."""

    model_config = ConfigDict(strict=True, extra="forbid")

    task_id: str = Field(description="Identificatore univoco del task")
    lane_id: Optional[str] = Field(default=None, description="Lane assegnata al writer o esplicita")
    target_repo_root: str = Field(default="", description="Root repository target normalizzata")
    declared_write_set: List[str] = Field(default_factory=list, description="Percorsi relativi dichiarati in scrittura")
    is_read_only: bool = Field(default=False, description="True se il nodo non dichiara scritture")


class ParallelWave(BaseModel):
    """Singola ondata di esecuzione parallela disgiunta."""

    model_config = ConfigDict(strict=True, extra="forbid")

    wave_index: int = Field(ge=0, description="Indice ordinale dell'ondata")
    tasks: List[WaveTaskAssignment] = Field(default_factory=list, description="Task pianificati nell'ondata")


class ParallelWavePlan(BaseModel):
    """Piano completo a ondate del DAG senza conflitti di scrittura."""

    model_config = ConfigDict(strict=True, extra="forbid")

    waves: List[ParallelWave] = Field(default_factory=list, description="Sequenza ordinata delle ondate")
    total_tasks: int = Field(ge=0, description="Numero totale dei task nel piano")
    max_lanes: int = Field(ge=1, description="Limite massimo di lane writer per ondata")


def _norm_repo_key(raw: Optional[str]) -> str:
    return (raw or "").strip().replace("\\", "/").rstrip("/").casefold()


def _norm_rel_key(raw: str) -> str:
    return raw.strip().replace("\\", "/").lstrip("./").casefold()


def _node_write_keys(node: TaskDAGNode) -> Set[WriteKey]:
    repo_k = _norm_repo_key(node.target_repo_root)
    return {(repo_k, rk) for item in node.declared_write_set if (rk := _norm_rel_key(item))}


def _validate_dag_topology(nodes: Sequence[TaskDAGNode]) -> Tuple[Dict[str, TaskDAGNode], Dict[str, List[str]], Dict[str, int]]:
    """Valida unicita ID, esistenza genitori e aciclicita tramite Kahn."""
    node_map: Dict[str, TaskDAGNode] = {}
    for node in nodes:
        if node.task_id in node_map:
            raise ValueError(f"Duplicate task_id in DAG: {node.task_id}")
        node_map[node.task_id] = node

    adj: Dict[str, List[str]] = {tid: [] for tid in node_map}
    in_deg: Dict[str, int] = {tid: 0 for tid in node_map}
    for tid, node in node_map.items():
        seen_parents: Set[str] = set()
        for pid in node.parent_ids:
            if pid not in node_map:
                raise ValueError(f"Missing parent task_id {pid!r} for task {tid!r}")
            if pid not in seen_parents:
                adj[pid].append(tid)
                in_deg[tid] += 1
                seen_parents.add(pid)

    check_deg = dict(in_deg)
    queue = [tid for tid, deg in check_deg.items() if deg == 0]
    visited = 0
    while queue:
        curr = queue.pop(0)
        visited += 1
        for child in adj[curr]:
            check_deg[child] -= 1
            if check_deg[child] == 0:
                queue.append(child)
    if visited != len(node_map):
        raise ValueError("DAG cycle detected during Kahn wave scheduling")
    return node_map, adj, in_deg


def _assign_lane(node: TaskDAGNode, prefix: str, wave_idx: int, slot_idx: int, is_ro: bool) -> Optional[str]:
    if node.lane_id is not None:
        return validate_lane_id(node.lane_id)
    if is_ro:
        return None
    clean_p = validate_lane_id(prefix)[:24]
    return validate_lane_id(f"{clean_p}_{wave_idx}_{slot_idx}")


def _pack_ready_batch(
    ready_ids: Sequence[str],
    node_map: Dict[str, TaskDAGNode],
    blocked_writes: Set[WriteKey],
    *,
    wave_idx: int,
    max_lanes: int,
    prefix: str,
) -> Tuple[List[WaveTaskAssignment], List[str]]:
    """Impacchetta in ordine deterministico i task ready disgiunti fino a max_lanes writer."""
    assigned: List[WaveTaskAssignment] = []
    deferred: List[str] = []
    used_writes = set(blocked_writes)
    writer_slots = 0

    for tid in sorted(ready_ids):
        node = node_map[tid]
        w_keys = _node_write_keys(node)
        is_ro = len(w_keys) == 0
        if not is_ro and (writer_slots >= max_lanes or bool(w_keys & used_writes)):
            deferred.append(tid)
            continue
        lane_val = _assign_lane(node, prefix, wave_idx, writer_slots, is_ro)
        if not is_ro:
            used_writes.update(w_keys)
            writer_slots += 1
        assigned.append(
            WaveTaskAssignment(
                task_id=node.task_id,
                lane_id=lane_val,
                target_repo_root=_norm_repo_key(node.target_repo_root),
                declared_write_set=sorted({rk for _repo, rk in w_keys}),
                is_read_only=is_ro,
            )
        )
    return assigned, deferred


def compute_parallel_waves(
    nodes: Sequence[TaskDAGNode],
    *,
    parent_lane_prefix: str = "w",
    max_lanes: int = 8,
) -> ParallelWavePlan:
    """Calcola la sequenza di ondate parallele Kahn disgiunte per write-set e multi-repo."""
    if int(max_lanes) < 1:
        raise ValueError(f"max_lanes must be >= 1, got {max_lanes}")
    norm_prefix = validate_lane_id(parent_lane_prefix)
    node_map, adj, in_deg = _validate_dag_topology(nodes)

    ready = sorted(tid for tid, deg in in_deg.items() if deg == 0)
    waves: List[ParallelWave] = []
    wave_idx = 0
    while ready:
        wave_tasks, deferred = _pack_ready_batch(
            ready, node_map, set(), wave_idx=wave_idx, max_lanes=int(max_lanes), prefix=norm_prefix
        )
        if not wave_tasks:
            raise ValueError("Unable to pack any ready task within max_lanes constraint")
        waves.append(ParallelWave(wave_index=wave_idx, tasks=wave_tasks))
        next_ready = list(deferred)
        for item in wave_tasks:
            for child in adj[item.task_id]:
                in_deg[child] -= 1
                if in_deg[child] == 0:
                    next_ready.append(child)
        ready = sorted(next_ready)
        wave_idx += 1

    return ParallelWavePlan(waves=waves, total_tasks=len(node_map), max_lanes=int(max_lanes))


def get_ready_wave(
    nodes: Sequence[TaskDAGNode],
    completed_ids: Collection[str],
    running_ids: Collection[str],
    *,
    max_lanes: int = 4,
    parent_lane_prefix: str = "w",
) -> ParallelWave:
    """Restituisce la prossima ondata eseguibile escludendo conflitti con i task running."""
    if int(max_lanes) < 1:
        raise ValueError(f"max_lanes must be >= 1, got {max_lanes}")
    norm_prefix = validate_lane_id(parent_lane_prefix)
    node_map, _adj, _deg = _validate_dag_topology(nodes)
    done_set = set(completed_ids)
    run_set = set(running_ids)

    blocked_writes: Set[WriteKey] = set()
    for r_id in run_set:
        if r_id in node_map:
            blocked_writes.update(_node_write_keys(node_map[r_id]))

    ready = [
        tid
        for tid, node in node_map.items()
        if tid not in done_set and tid not in run_set and all(pid in done_set for pid in node.parent_ids)
    ]
    tasks, _deferred = _pack_ready_batch(
        ready, node_map, blocked_writes, wave_idx=0, max_lanes=int(max_lanes), prefix=norm_prefix
    )
    return ParallelWave(wave_index=0, tasks=tasks)
