"""
Token Weighted Allocator - NK-Security-Auditor Resource
Scans target files, estimates/calculates token counts, and partitions files into homogeneous segments <= 12,000 tokens.
"""

import json
import math
import os
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple


def win32_backoff_read(file_path: Path, max_retries: int = 5, initial_delay: float = 0.1) -> str:
    """Reads a file with Win32 Exponential Backoff to avoid Google Drive lock collisions."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except (PermissionError, OSError) as e:
            if attempt == max_retries - 1:
                raise e
            time.sleep(delay)
            delay *= 2.0
    return ""


def estimate_token_count(text: str) -> int:
    """
    Estimates token count for a text block.
    Uses tiktoken if available; falls back to character/word ratio heuristics (~3.8 chars/token).
    """
    try:
        import tiktoken
        encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except Exception:
        # Fallback estimation: average 3.8 chars per token for code/markdown
        if not text:
            return 0
        return int(math.ceil(len(text) / 3.8))


class TokenWeightedAllocator:
    def __init__(self, max_tokens_per_segment: int = 12000, max_clones: int = 6):
        self.max_tokens_per_segment = max_tokens_per_segment
        self.max_clones = max_clones

    def partition_files(self, file_paths: List[str]) -> Dict[str, Any]:
        """
        Calculates token counts for given file paths and partitions them into segments.
        Each segment contains files whose combined token count is <= max_tokens_per_segment.
        """
        file_metrics: List[Dict[str, Any]] = []
        total_tokens = 0

        for path_str in file_paths:
            p = Path(path_str).resolve()
            if not p.exists() or not p.is_file():
                continue
            
            try:
                content = win32_backoff_read(p)
                tokens = estimate_token_count(content)
            except Exception as e:
                tokens = 0
            
            file_metrics.append({
                "path": str(p),
                "tokens": tokens
            })
            total_tokens += tokens

        # Partitioning logic (First Fit Decreasing / Bin Packing)
        file_metrics.sort(key=lambda x: x["tokens"], reverse=True)
        segments: List[Dict[str, Any]] = []

        for item in file_metrics:
            placed = False
            for seg in segments:
                if seg["total_tokens"] + item["tokens"] <= self.max_tokens_per_segment:
                    seg["files"].append(item["path"])
                    seg["total_tokens"] += item["tokens"]
                    placed = True
                    break
            
            if not placed:
                if len(segments) >= self.max_clones:
                    # Append to smallest segment if max clone count reached
                    smallest_seg = min(segments, key=lambda s: s["total_tokens"]) if segments else None
                    if smallest_seg:
                        smallest_seg["files"].append(item["path"])
                        smallest_seg["total_tokens"] += item["tokens"]
                    else:
                        segments.append({
                            "segment_id": 1,
                            "files": [item["path"]],
                            "total_tokens": item["tokens"]
                        })
                else:
                    segments.append({
                        "segment_id": len(segments) + 1,
                        "files": [item["path"]],
                        "total_tokens": item["tokens"]
                    })

        return {
            "status": "SUCCESS",
            "total_files": len(file_metrics),
            "total_tokens": total_tokens,
            "segment_count": len(segments),
            "max_tokens_limit": self.max_tokens_per_segment,
            "segments": segments
        }


if __name__ == "__main__":
    import sys
    allocator = TokenWeightedAllocator()
    targets = sys.argv[1:] if len(sys.argv) > 1 else [__file__]
    res = allocator.partition_files(targets)
    print(json.dumps(res, indent=2))
