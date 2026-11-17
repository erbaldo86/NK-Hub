# -*- coding: utf-8 -*-
"""Parser CLI e punto di ingresso lazy per memory_3tier_engine."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any


def _build_cli_parser() -> Any:
    """Costruisce il parser CLI senza importare pydantic su --help."""
    parser = argparse.ArgumentParser(
        description="Motore di Memoria Episodica a 3 Livelli NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default=None,
        help="Directory base della memoria episodica",
    )
    parser.add_argument(
        "--recall",
        action="store_true",
        help="Esegue una ricerca ibrida RRF nel dominio",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Aggiunge un nuovo episodio e sincronizza la capsula Tier-1",
    )
    parser.add_argument(
        "--tier1-sync",
        action="store_true",
        help="Sincronizza e persiste tier1_active_capsule.json",
    )
    parser.add_argument(
        "--consolidate",
        action="store_true",
        help="Consolida gli episodi simili in modo deterministico Zero-LLM",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.92,
        help="Soglia di similarita coseno per il consolidamento (default: 0.92)",
    )
    parser.add_argument(
        "--domain",
        type=str,
        default="02_Development_Patterns",
        help="Dominio NK o alias breve (OPS, ARCH, DEVX, SEC)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Query di ricerca per --recall",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="Lesson Learned",
        help="Titolo dell'episodio per --append",
    )
    parser.add_argument(
        "--content",
        type=str,
        default="",
        help="Contenuto dell'episodio per --append",
    )
    parser.add_argument(
        "--tags",
        type=str,
        default="",
        help="Tag separati da virgola per --append",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="Profilo di budget token (standard, generation, carbon o argon)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Percorso di output personalizzato per tier1_active_capsule.json",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Stampa il risultato in formato JSON",
    )
    return parser


def main() -> int:
    """Interfaccia CLI per il motore di memoria a 3 livelli."""
    parser = _build_cli_parser()
    args = parser.parse_args()

    from _internal.memory_3tier_engine.engine_core import ThreeTierMemoryEngine
    from _internal.memory_3tier_engine.models import (
        MemoryEpisode,
        _facade_attr,
        _workspace_root,
        resolve_domain,
    )

    ws_root = Path(_facade_attr("_workspace_root", _workspace_root))
    base_path = (
        Path(args.base_dir).resolve()
        if args.base_dir
        else (ws_root / "nk_tracking" / "memory_3tier")
    )
    raw_prof = args.profile or os.environ.get("NK_MODEL_PROFILE")
    active_profile = (
        raw_prof.strip().lower()
        if isinstance(raw_prof, str) and raw_prof.strip()
        else None
    )
    eng_cls = _facade_attr("ThreeTierMemoryEngine", ThreeTierMemoryEngine)
    engine = eng_cls(base_dir=base_path, profile=active_profile)

    if args.append:
        tag_list = [t.strip() for t in args.tags.split(",") if t.strip()]
        ep = MemoryEpisode(
            episode_id=f"ep_{int(time.time())}_{uuid.uuid4().hex[:6]}",
            domain=args.domain,
            title=args.title,
            content=args.content or args.title,
            tags=tag_list,
        )
        engine.append_episode(ep)
        capsule = engine.sync_tier1_capsule(
            output_path=args.output, profile=active_profile
        )
        out = {
            "status": "APPENDED",
            "episode_id": ep.episode_id,
            "domain": ep.domain,
            "tier1_synced": True,
            "token_cap": capsule["token_cap"],
        }
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"[MEMORY-3TIER] Episodio salvato: {ep.episode_id} ({ep.domain})")
        return 0

    if args.tier1_sync:
        capsule = engine.sync_tier1_capsule(
            output_path=args.output, profile=active_profile
        )
        if args.json:
            print(json.dumps(capsule, indent=2))
        else:
            print(
                f"[MEMORY-3TIER] tier1_active_capsule.json sincronizzato (cap={capsule['token_cap']})."
            )
        return 0

    if args.consolidate:
        cons_dom = args.domain if "--domain" in sys.argv else None
        cons_res = engine.consolidate_similar_episodes(
            domain=cons_dom, threshold=float(args.threshold)
        )
        if args.json:
            print(json.dumps(cons_res, indent=2))
        else:
            print(
                f"[MEMORY-3TIER] Consolidamento completato: {cons_res['merged_count']} uniti, {cons_res['remaining_count']} attivi."
            )
        return 0

    if args.recall:
        hits = engine.recall_hybrid(domain=args.domain, query=args.query)
        payload = {
            "status": "OK",
            "domain": resolve_domain(args.domain),
            "query": args.query,
            "results": [
                {
                    "episode_id": ep.episode_id,
                    "title": ep.title,
                    "content": ep.content,
                    "score": round(score, 6),
                }
                for ep, score in hits
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            for ep, score in hits:
                print(
                    f"[{round(score, 4)}] {ep.episode_id}: {ep.title} -> {ep.content}"
                )
        return 0

    capsule = engine.sync_tier1_capsule(
        output_path=args.output, profile=active_profile
    )
    if args.json:
        print(json.dumps(capsule, indent=2))
    else:
        print(f"[MEMORY-3TIER] Ready. Base dir: {base_path}")
    return 0
