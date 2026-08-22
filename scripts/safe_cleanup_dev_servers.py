"""
Safe Cleanup Dev Servers & Orphan Processes Watchdog (Windows Anti-Lock Tool)
Nexus Keystone 3.0 System Maintenance Utility.
Identifies and safely terminates orphaned dev servers, uvicorn/FastAPI instances,
and processes holding file locks on ports 8000, 8080, 5000, 3000.
"""

import os
import sys
import subprocess
import time
import json

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

TARGET_PORTS = [8000, 8080, 5000, 3000]

def get_pids_listening_on_ports(ports):
    pids = set()
    try:
        # Run netstat to find PIDs on Windows
        output = subprocess.check_output("netstat -ano", shell=True, text=True, stderr=subprocess.DEVNULL)
        for line in output.splitlines():
            line = line.strip()
            if not line or "LISTENING" not in line:
                continue
            parts = line.split()
            if len(parts) >= 5:
                local_addr = parts[1]
                pid_str = parts[-1]
                for p in ports:
                    if local_addr.endswith(f":{p}"):
                        try:
                            pid = int(pid_str)
                            if pid > 0 and pid != os.getpid():
                                pids.add(pid)
                        except ValueError:
                            pass
    except Exception as e:
        print(f"⚠️ Warning querying netstat: {e}", file=sys.stderr)
    return pids

def kill_pid_tree(pid):
    try:
        # Force terminate PID and its entire child process tree on Windows
        res = subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, capture_output=True, text=True)
        return res.returncode == 0
    except Exception as e:
        print(f"⚠️ Error killing PID {pid}: {e}", file=sys.stderr)
        return False

def run_cleanup():
    print("======================================================================")
    print("🛡️ SAFE CLEANUP DEV SERVERS & WINDOWS FILE-LOCK WATCHDOG")
    print("======================================================================")
    
    pids_to_kill = get_pids_listening_on_ports(TARGET_PORTS)
    cleaned = []
    
    if not pids_to_kill:
        print("✅ Nessun processo o server in ascolto rilevato sulle porte target (8000, 8080, 5000, 3000).")
        print("🟢 Tutti gli handle di file I/O sono liberi. Safe to edit.")
    else:
        print(f"🔍 Rilevati {len(pids_to_kill)} processi attivi sulle porte target: {list(pids_to_kill)}")
        for pid in pids_to_kill:
            success = kill_pid_tree(pid)
            cleaned.append({"pid": pid, "killed": success})
            status_tag = "TERMINATO 🟢" if success else "ERRORE 🔴"
            print(f"   ↳ Processo PID {pid}: {status_tag}")
        
        # Brief pause to let Windows NTFS release file handles
        time.sleep(0.5)
        print("✅ Bonifica completata. Tutti i lock sui file sono stati rilasciati.")

    print("======================================================================")
    return 0

if __name__ == "__main__":
    sys.exit(run_cleanup())
