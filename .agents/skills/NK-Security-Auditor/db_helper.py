import sqlite3
import argparse
import os
import datetime

def init_db(db_path):
    conn = sqlite3.connect(db_path, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA busy_timeout = 5000;')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            target_file TEXT NOT NULL,
            status TEXT NOT NULL,
            score REAL,
            roi REAL
        )
    ''')
    conn.commit()
    return conn

def log_audit(db_path, target_file, status, score, roi):
    conn = init_db(db_path)
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().isoformat()
    cursor.execute('''
        INSERT INTO audit_logs (timestamp, target_file, status, score, roi)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, target_file, status, score, roi))
    conn.commit()
    conn.close()
    print(f"Logged audit per {target_file}: Status={status}, Score={score}, ROI={roi}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="NK-Security-Auditor SQLite storaging helper.")
    parser.add_argument('--file', required=True, help="Target file path")
    parser.add_argument('--status', required=True, help="Status of the audit")
    parser.add_argument('--score', type=float, default=0.0, help="Evaluator score")
    parser.add_argument('--roi', type=float, default=0.0, help="ROI metric")
    
    args = parser.parse_args()
    
    workspace_root = os.environ.get("WORKSPACE_ROOT")
    if not workspace_root:
        workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    db_path = os.path.join(workspace_root, "nk_tracking", "nk_tas_roi.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    log_audit(db_path, args.file, args.status, args.score, args.roi)
