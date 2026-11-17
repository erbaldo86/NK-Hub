"""
NK Hub Generation 1.0.0-Generation: High-Density AST Repo-Map Engine.
Modulo: scripts/ast_repo_mapper.py.
@domain_id: DOM-02

Funzionalita principali:
* Genera il grafo dei simboli (Python AST e Polyglot JS/TS/CSS/HTML).
* Calcola Personalized PageRank (d=0.85) con vettore di teletrasporto multi-focale.
* Esegue lo slicing chirurgico Karpathy preservando i parametri esatti.
* Applica il clustering gerarchico a due livelli contro la diluizione dei token.
* Gestisce la cache incrementale per file (nodi ed archi) con rename atomico in %TEMP%.
* Adatta il budget token per skill (Mode C/B/A e profili Generation, Carbon e Argon).
* Esporta autonomamente lo snapshot in nk_genome/repo_map.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROD_SCRIPTS = (
    _SCRIPT_DIR.parent.parent / "scripts"
    if _SCRIPT_DIR.parent.name == ".staging"
    else _SCRIPT_DIR
)
for _p in (str(_PROD_SCRIPTS), str(_SCRIPT_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
if _SCRIPT_DIR != _PROD_SCRIPTS and (_SCRIPT_DIR / "_internal" / "nk_common").is_dir():
    import _internal as _stg_int, _internal.nk_common as _stg_nkc

    for _pkg_obj, _stg_dir in (
        (_stg_int, str(_SCRIPT_DIR / "_internal")),
        (_stg_nkc, str(_SCRIPT_DIR / "_internal" / "nk_common")),
    ):
        _cur_p = list(getattr(_pkg_obj, "__path__", ()))
        _pkg_obj.__path__ = [_stg_dir] + [p for p in _cur_p if os.path.normcase(p) != os.path.normcase(_stg_dir)]

from _internal.nk_common.facade_boot import init_nk_facade  # noqa: E402
from _internal.nk_common.paths import reconfigure_streams  # noqa: E402

init_nk_facade(__file__, pkg="ast_repo_mapper")

_EXPORTS_LOADED = False


def _ensure_exports_loaded() -> Dict[str, Any]:
    """Carica pigramente i sottomoduli AST Repo-Map evitando import Pydantic su --help."""
    global _EXPORTS_LOADED
    if _EXPORTS_LOADED:
        return globals()

    from _internal.ast_repo_mapper.generator import RepoMapGenerator
    from _internal.ast_repo_mapper.models import (
        CACHE_SCHEMA_VERSION,
        DEFAULT_EXCLUDED_DIRS,
        EdgeType,
        PageRankResult,
        RepoMapConfig,
        RepoMapResult,
        SliceResult,
        SymbolEdge,
        SymbolGraph,
        SymbolNode,
        SymbolType,
        estimate_tokens,
    )
    from _internal.ast_repo_mapper.parser_resilient import ResilientParser
    from _internal.ast_repo_mapper.polyglot_and_cache import (
        AtomicCacheManager,
        GraduatedSkillAdapter,
        PolyglotExtractor,
    )
    from _internal.ast_repo_mapper.ranking_and_slicing import (
        KarpathySurgicalSlicer,
        PersonalizedPageRank,
    )
    from _internal.ast_repo_mapper.subgraph_query import (
        export_markdown_snapshot,
        query_symbol_subgraph,
    )
    from _internal.ast_repo_mapper.symbol_extractor import SymbolExtractor

    exported: Dict[str, Any] = {
        "RepoMapGenerator": RepoMapGenerator,
        "CACHE_SCHEMA_VERSION": CACHE_SCHEMA_VERSION,
        "DEFAULT_EXCLUDED_DIRS": DEFAULT_EXCLUDED_DIRS,
        "EdgeType": EdgeType,
        "PageRankResult": PageRankResult,
        "RepoMapConfig": RepoMapConfig,
        "RepoMapResult": RepoMapResult,
        "SliceResult": SliceResult,
        "SymbolEdge": SymbolEdge,
        "SymbolGraph": SymbolGraph,
        "SymbolNode": SymbolNode,
        "SymbolType": SymbolType,
        "estimate_tokens": estimate_tokens,
        "ResilientParser": ResilientParser,
        "AtomicCacheManager": AtomicCacheManager,
        "GraduatedSkillAdapter": GraduatedSkillAdapter,
        "PolyglotExtractor": PolyglotExtractor,
        "KarpathySurgicalSlicer": KarpathySurgicalSlicer,
        "PersonalizedPageRank": PersonalizedPageRank,
        "export_markdown_snapshot": export_markdown_snapshot,
        "query_symbol_subgraph": query_symbol_subgraph,
        "SymbolExtractor": SymbolExtractor,
    }
    globals().update(exported)
    _EXPORTS_LOADED = True
    return globals()


def __getattr__(name: str) -> Any:
    """Espone in modo trasparente la facciata AST Repo-Map al primo accesso."""
    ns = _ensure_exports_loaded()
    if name in ns:
        return ns[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    reconfigure_streams()

    parser = argparse.ArgumentParser(description="High-Density AST Repo-Map Engine 1.0.0-Generation")
    parser.add_argument("--repo-map", action="store_true", help="Genera e stampa la repo map")
    parser.add_argument("--root", default=".", help="Directory radice da analizzare")
    parser.add_argument("--max-tokens", type=int, default=None, help="Budget massimo di token")
    parser.add_argument(
        "--mode",
        default="auto",
        help="Modalita: auto, mode_c, mode_b, mode_a, generation_mode_*, carbon_mode_*, argon_mode_*",
    )
    parser.add_argument("--json", action="store_true", help="Output in formato JSON")
    parser.add_argument("--snapshot-out", "--export", dest="snapshot_out", type=str, help="Esporta snapshot su file")
    parser.add_argument("--focus-files", type=str, default="", help="Lista di file focali separati da virgola")
    parser.add_argument("--symbol", type=str, default=None, help="Interroga il sottografo AST per un singolo simbolo senza rigenerare repo_map.md")

    args = parser.parse_args()
    _ensure_exports_loaded()
    from _internal.ast_repo_mapper.generator import RepoMapGenerator
    from _internal.ast_repo_mapper.models import RepoMapConfig
    from _internal.ast_repo_mapper.polyglot_and_cache import GraduatedSkillAdapter
    from _internal.ast_repo_mapper.subgraph_query import query_symbol_subgraph

    root_path = Path(args.root).resolve()
    if args.root == "." and not (root_path / "scripts").is_dir() and (root_path / "NK_Hub" / "scripts").is_dir():
        root_path = (root_path / "NK_Hub").resolve()

    if args.symbol:
        sub_res = query_symbol_subgraph(symbol_name=args.symbol, root=root_path)
        print(json.dumps(sub_res, indent=2, ensure_ascii=False))
        return

    focals = [f.strip() for f in args.focus_files.split(",") if f.strip()]

    effective_tokens = (
        args.max_tokens
        if args.max_tokens is not None
        else (
            2400
            if args.snapshot_out and args.mode == "auto"
            else (
                1100
                if args.repo_map and args.mode == "auto"
                else GraduatedSkillAdapter.get_token_budget("NK-Orchestrator", args.mode)
            )
        )
    )

    cfg = RepoMapConfig(
        max_tokens=effective_tokens,
        mode=args.mode,
        focal_files=focals,
        polyglot=True,
    )

    result = RepoMapGenerator.generate(root_dir=root_path, config=cfg)

    if args.snapshot_out:
        out_p = Path(args.snapshot_out).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(result.content, encoding="utf-8")
        print(f"[+] Snapshot saved to: {out_p} ({result.token_count} tokens, {result.elapsed_ms}ms)")

    if args.json:
        print(json.dumps(result.model_dump(), indent=2))
    elif args.repo_map or not args.snapshot_out:
        safe_text = result.content.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(
            sys.stdout.encoding or "utf-8"
        )
        print(safe_text)


if __name__ == "__main__":
    main()
