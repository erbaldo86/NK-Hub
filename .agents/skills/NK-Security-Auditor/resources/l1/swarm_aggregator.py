"""
Swarm Aggregator - NK-Security-Auditor Resource
Merges clone output JSONs, combines Threat Heatmaps, and records transactional results into SQLite WAL DB.
"""

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any


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


class SwarmAggregator:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initializes SQLite DB in WAL mode."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swarm_audit_runs (
                    run_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_threats INTEGER NOT NULL,
                    heatmap_json TEXT NOT NULL,
                    report_json TEXT NOT NULL
                );
            """)
            conn.commit()
        finally:
            conn.close()

    def aggregate_clone_outputs(self, ipc_dir: Path, run_id: str) -> Dict[str, Any]:
        """
        Reads worker_*.json outputs from ipc_dir, merges threat heatmaps,
        and saves aggregated results to SQLite WAL DB and file.
        """
        worker_files = list(ipc_dir.glob("worker_*.json"))
        aggregated_threats: List[Dict[str, Any]] = []
        threat_heatmap: Dict[str, int] = {}
        processed_workers: List[str] = []

        for w_file in worker_files:
            try:
                with open(w_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                worker_id = data.get("worker_id", w_file.stem)
                processed_workers.append(worker_id)

                threats = data.get("threats", [])
                for t in threats:
                    aggregated_threats.append(t)
                    severity = t.get("severity", "UNKNOWN").upper()
                    threat_heatmap[severity] = threat_heatmap.get(severity, 0) + 1
            except Exception as e:
                threat_heatmap["ERROR_PARSING"] = threat_heatmap.get("ERROR_PARSING", 0) + 1

        aggregated_report = {
            "status": "SUCCESS",
            "run_id": run_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "worker_count": len(processed_workers),
            "workers_processed": processed_workers,
            "total_threats": len(aggregated_threats),
            "threat_heatmap": threat_heatmap,
            "threats": aggregated_threats
        }

        # Save to SQLite WAL
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                INSERT OR REPLACE INTO swarm_audit_runs (run_id, timestamp, status, total_threats, heatmap_json, report_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                run_id,
                aggregated_report["timestamp"],
                aggregated_report["status"],
                aggregated_report["total_threats"],
                json.dumps(threat_heatmap),
                json.dumps(aggregated_report)
            ))
            conn.commit()
        finally:
            conn.close()

        # Save aggregated result to JSON
        output_json = ipc_dir / "aggregated_result.json"
        win32_backoff_write(output_json, json.dumps(aggregated_report, indent=2))

        return aggregated_report


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db_p = Path(tmpdir) / "audit.db"
        agg = SwarmAggregator(db_p)
        ipc = Path(tmpdir) / "ipc"
        ipc.mkdir()
        (ipc / "worker_1.json").write_text(json.dumps({
            "worker_id": "worker_1",
            "threats": [{"id": "T1", "severity": "HIGH", "file": "a.py"}]
        }))
        res = agg.aggregate_clone_outputs(ipc, "test_run_001")
        print(json.dumps(res, indent=2))
