#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Formattatore messaggi Swarm per NK Hub Generation 1.0.0-Generation.
Modulo: nk_swarm_messenger.py.
Applica la regola [RULE-SWARM-HYGIENE] e la guardia GT-04 (limite MSS di 1800 caratteri).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

_scripts_dir = Path(__file__).resolve().parent
_workspace_root = (
    _scripts_dir.parent.parent
    if _scripts_dir.parent.name == ".staging"
    else _scripts_dir.parent
)
if str(_workspace_root) not in sys.path:
    sys.path.insert(0, str(_workspace_root))
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))
if _scripts_dir.parent.name == ".staging" and (_scripts_dir / "_internal").is_dir():
    import _internal as _stg_internal_pkg

    _stg_int_str = str(_scripts_dir / "_internal")
    if _stg_int_str not in _stg_internal_pkg.__path__:
        _stg_internal_pkg.__path__.insert(0, _stg_int_str)

from _internal.nk_common.io import atomic_write_text  # noqa: E402
from _internal.nk_common.paths import reconfigure_streams  # noqa: E402

SWARM_MSS_LIMIT: int = 1800


def process_payload(
    payload: str,
    sender: Optional[str] = None,
    recipient: Optional[str] = None,
) -> str:
    """Applica il taglio MSS a 1800 caratteri dopo la formattazione dell'envelop e salva il payload completo su disco."""
    reconfigure_streams()
    header = ""
    if sender or recipient:
        src = sender or "subagent"
        dst = recipient or "parent"
        header = f"[Swarm-Envelope: {src} -> {dst}]\n"

    full_text = f"{header}{payload}" if header else payload
    if len(full_text) <= SWARM_MSS_LIMIT:
        return full_text

    sha256 = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    temp_dir = os.path.join(tempfile.gettempdir(), "nk_diagnostics")
    os.makedirs(temp_dir, exist_ok=True)
    dump_file = os.path.join(temp_dir, f"swarm_spillover_{sha256[:8]}.txt")

    ok, err = atomic_write_text(dump_file, full_text)
    if not ok:
        raise OSError(err or f"Atomic write failed for swarm spillover: {dump_file}")

    head = full_text[:400]
    tail = full_text[-800:]

    return f"{head}\n\n[...TRUNCATED, FULL PAYLOAD SAVED TO {dump_file}...]\n\n{tail}"


def main() -> None:
    reconfigure_streams()
    parser = argparse.ArgumentParser(
        description="Formattatore Messaggi Swarm NK Hub Generation 1.0.0-Generation"
    )
    parser.add_argument("--sender", default=None)
    parser.add_argument("--recipient", default=None)
    parser.add_argument("--payload", default=None)
    parser.add_argument("--payload-file", default=None)
    args = parser.parse_args()

    payload = ""
    if args.payload:
        payload = args.payload
    elif args.payload_file:
        with open(args.payload_file, "r", encoding="utf-8") as f:
            payload = f.read()

    result = process_payload(payload, sender=args.sender, recipient=args.recipient)
    print(result)


if __name__ == "__main__":
    main()
